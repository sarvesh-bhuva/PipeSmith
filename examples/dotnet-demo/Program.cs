var app = WebApplication.CreateBuilder(args).Build();
app.MapGet("/", () => Newtonsoft.Json.JsonConvert.SerializeObject(new { app = "pipesmith-dotnet-demo", ok = true }));
app.Run();
