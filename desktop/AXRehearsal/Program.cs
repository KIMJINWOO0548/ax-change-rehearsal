using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media.Imaging;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace AXRehearsal;

internal sealed class WorkbenchWindow : Window
{
    private readonly string profile;
    private readonly WebView2 view = new();
    private readonly TextBlock state = new() { Margin = new Thickness(24), TextWrapping = TextWrapping.Wrap };
    private readonly CancellationTokenSource closing = new();
    private Process? backend;

    [STAThread]
    public static void Main(string[] args)
    {
        var app = new Application();
        if (args is not ([] or ["--profile", _]))
        {
            MessageBox.Show("사용 가능한 옵션은 --profile <폴더>입니다.", "AX Change Rehearsal");
            return;
        }
        var path = args.Length == 0
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AXChangeRehearsal")
            : Path.GetFullPath(args[1]);
        app.Run(new WorkbenchWindow(path));
    }

    private WorkbenchWindow(string profile)
    {
        this.profile = profile;
        Title = "AX Change Rehearsal · 합성 정책 리허설";
        Icon = BitmapFrame.Create(new Uri("pack://application:,,,/Assets/axrehearsal.ico"));
        Width = 1370; Height = 850; MinWidth = 620; MinHeight = 440;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        AutomationProperties.SetLiveSetting(state, AutomationLiveSetting.Polite);
        state.Text = "로컬 리허설 엔진을 시작하는 중입니다…";
        Content = state;
        Loaded += Start;
        Closed += (_, _) => Stop();
    }

    private async void Start(object sender, RoutedEventArgs args)
    {
        Loaded -= Start;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(closing.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(25));
        var token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        try
        {
            Directory.CreateDirectory(profile);
            var start = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "python", "python.exe"))
            {
                WorkingDirectory = AppContext.BaseDirectory, UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, StandardInputEncoding = new UTF8Encoding(false)
            };
            foreach (var argument in new[] { "-E", "-s", "-B", "-u", Path.Combine(AppContext.BaseDirectory, "desktop_workbench.py"),
                         Path.Combine(profile, "Evidence") })
                start.ArgumentList.Add(argument);
            var process = Process.Start(start) ?? throw new IOException("Local engine unavailable");
            backend = process;
            await process.StandardInput.WriteAsync(token + "\n");
            await process.StandardInput.FlushAsync();
            if (!int.TryParse(await process.StandardOutput.ReadLineAsync(timeout.Token), out int port) || port is < 1 or > 65535)
                throw new IOException("Invalid local engine port");
            var origin = new Uri($"http://127.0.0.1:{port}/");
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: Path.Combine(profile, "WebView2"))
                .WaitAsync(timeout.Token);
            Content = view;
            await view.EnsureCoreWebView2Async(environment).WaitAsync(timeout.Token);
            Connect(view.CoreWebView2, origin, token);
            view.CoreWebView2.Navigate(origin.AbsoluteUri);
        }
        catch (Exception) when (closing.IsCancellationRequested) { }
        catch (Exception)
        {
            state.Text = "로컬 리허설 작업대를 열 수 없습니다.\n압축을 모두 풀었는지, WebView2 Runtime과 로컬 폴더를 사용할 수 있는지 확인한 뒤 다시 실행하세요.";
            Content = state;
            CloseBackend();
        }
    }

    private static void Connect(CoreWebView2 core, Uri origin, string token)
    {
        bool IsLocal(string value) => Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme == origin.Scheme &&
            uri.Host == origin.Host && uri.Port == origin.Port && uri.UserInfo.Length == 0;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.IsPasswordAutosaveEnabled = false;
        core.Settings.IsGeneralAutofillEnabled = false;
        core.NavigationStarting += (_, e) => e.Cancel = !IsLocal(e.Uri);
        core.FrameNavigationStarting += (_, e) => e.Cancel = true;
        core.NewWindowRequested += (_, e) => e.Handled = true;
        core.PermissionRequested += (_, e) => e.State = CoreWebView2PermissionState.Deny;
        core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All, CoreWebView2WebResourceRequestSourceKinds.All);
        core.WebResourceRequested += (_, e) =>
        {
            if (IsLocal(e.Request.Uri)) e.Request.Headers.SetHeader("X-AX-Desktop", token);
            else if (!e.Request.Uri.StartsWith("blob:" + origin.AbsoluteUri, StringComparison.Ordinal) &&
                     !e.Request.Uri.StartsWith("data:", StringComparison.Ordinal))
                e.Response = core.Environment.CreateWebResourceResponse(null, 403, "Local workspace only", "");
        };
    }

    private void Stop()
    {
        closing.Cancel();
        view.Dispose();
        CloseBackend();
    }

    private void CloseBackend()
    {
        if (backend is not { } process) return;
        backend = null;
        using (process)
        {
            if (process.HasExited) return;
            process.StandardInput.Close();
            if (!process.WaitForExit(6500)) process.Kill();
        }
    }
}
