from fastapi import FastAPI
from fastapi.responses import HTMLResponse


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Affiliate Agent Command Center</title>
  </head>
  <body>
    <main>
      <section>
        <h1>Command Center</h1>
      </section>
      <section>
        <h2>Approval Inbox</h2>
      </section>
      <section>
        <h2>Execution Timeline</h2>
      </section>
      <section>
        <h2>Guardrail Controls</h2>
      </section>
    </main>
  </body>
</html>
""".strip()


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return DASHBOARD_HTML

    @app.get("/telegram/health")
    async def telegram_health() -> dict[str, str]:
        return {"status": "ok"}

    return app
