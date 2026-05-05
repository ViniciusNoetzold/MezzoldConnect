import type { FastifyInstance } from 'fastify';

const dashboardHtml = String.raw`<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mezzold Connect Local</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f6f7f9;
        --panel: #ffffff;
        --text: #17202a;
        --muted: #667085;
        --border: #d8dee8;
        --primary: #176b87;
        --primary-hover: #11546a;
        --danger: #ba3535;
        --ok: #207a4c;
        --warn: #a76200;
        --shadow: 0 10px 30px rgba(22, 32, 42, 0.08);
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
          Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: 14px;
      }

      header {
        border-bottom: 1px solid var(--border);
        background: #ffffff;
      }

      .header-inner,
      main {
        width: min(1280px, calc(100vw - 32px));
        margin: 0 auto;
      }

      .header-inner {
        min-height: 64px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
      }

      h1 {
        margin: 0;
        font-size: 20px;
        font-weight: 700;
      }

      main {
        padding: 24px 0 36px;
        display: grid;
        grid-template-columns: 380px minmax(0, 1fr);
        gap: 20px;
      }

      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 8px;
        box-shadow: var(--shadow);
      }

      .panel-header {
        padding: 16px 18px;
        border-bottom: 1px solid var(--border);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }

      .panel-title {
        font-size: 15px;
        font-weight: 700;
      }

      .panel-body {
        padding: 18px;
      }

      .stack {
        display: grid;
        gap: 14px;
      }

      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
      }

      label {
        display: grid;
        gap: 6px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 650;
      }

      input,
      textarea,
      select {
        width: 100%;
        min-height: 38px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: #fff;
        color: var(--text);
        padding: 8px 10px;
        font: inherit;
      }

      textarea {
        min-height: 86px;
        resize: vertical;
      }

      button {
        min-height: 38px;
        border: 1px solid transparent;
        border-radius: 6px;
        background: var(--primary);
        color: #fff;
        padding: 8px 12px;
        font-weight: 700;
        cursor: pointer;
      }

      button:hover {
        background: var(--primary-hover);
      }

      button.secondary {
        background: #fff;
        color: var(--text);
        border-color: var(--border);
      }

      button.secondary:hover {
        background: #eef2f6;
      }

      button.danger {
        background: var(--danger);
      }

      button.full {
        width: 100%;
      }

      .button-row {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }

      .kpis {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
      }

      .kpi {
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 14px;
        background: #fbfcfe;
      }

      .kpi-value {
        font-size: 24px;
        font-weight: 800;
        line-height: 1.2;
      }

      .kpi-label {
        margin-top: 4px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 650;
      }

      .status-pill {
        display: inline-flex;
        align-items: center;
        min-height: 26px;
        border-radius: 999px;
        padding: 3px 10px;
        background: #eaf4ef;
        color: var(--ok);
        font-size: 12px;
        font-weight: 800;
      }

      .status-pill.warn {
        background: #fff5e7;
        color: var(--warn);
      }

      .status-pill.danger {
        background: #fdecec;
        color: var(--danger);
      }

      pre {
        margin: 0;
        max-height: 360px;
        overflow: auto;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: #101820;
        color: #e7edf4;
        padding: 14px;
        font-size: 12px;
        line-height: 1.5;
      }

      table {
        width: 100%;
        border-collapse: collapse;
      }

      th,
      td {
        padding: 10px 8px;
        border-bottom: 1px solid var(--border);
        text-align: left;
        vertical-align: middle;
      }

      th {
        color: var(--muted);
        font-size: 12px;
      }

      .table-wrap {
        overflow-x: auto;
      }

      .muted {
        color: var(--muted);
      }

      .toast {
        min-height: 28px;
        color: var(--muted);
        font-weight: 650;
      }

      @media (max-width: 980px) {
        main {
          grid-template-columns: 1fr;
        }

        .kpis {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
      }

      @media (max-width: 560px) {
        .header-inner,
        main {
          width: min(100vw - 20px, 1280px);
        }

        .grid,
        .kpis {
          grid-template-columns: 1fr;
        }

        .header-inner {
          align-items: flex-start;
          flex-direction: column;
          padding: 14px 0;
        }
      }
    </style>
  </head>
  <body>
    <header>
      <div class="header-inner">
        <h1>Mezzold Connect Local</h1>
        <span id="apiState" class="status-pill warn">checking</span>
      </div>
    </header>

    <main>
      <section class="stack">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Número</div>
          </div>
          <div class="panel-body stack">
            <label>
              Telefone do número
              <input id="phoneNumber" value="+5511999999999" />
            </label>
            <label>
              Nome para identificar
              <input id="displayName" value="Numero teste" />
            </label>
            <label>
              Link de teste do provedor
              <input id="webhookUrl" value="http://localhost:4000/messages" />
            </label>
            <button id="createNumber" class="full">Cadastrar número</button>
            <label>
              ID do número selecionado
              <input id="numberId" />
            </label>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Aquecimento</div>
          </div>
          <div class="panel-body stack">
            <label>
              Clientes de teste, um por linha
              <textarea id="recipients">+5511888887777</textarea>
            </label>
            <label>
              Mensagem
              <textarea id="template">{Oi|Ola} {{name}}, teste da plataforma {{company}}.</textarea>
            </label>
            <div class="grid">
              <label>
                name
                <input id="varName" value="Ana" />
              </label>
              <label>
                company
                <input id="varCompany" value="Mezzold Connect" />
              </label>
            </div>
            <div class="button-row">
              <button id="startWarmup">Iniciar</button>
              <button id="pauseWarmup" class="danger">Pausar</button>
              <button id="refresh" class="secondary">Atualizar</button>
            </div>
          </div>
        </div>
      </section>

      <section class="stack">
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Situação atual</div>
            <span id="numberStatus" class="status-pill warn">none</span>
          </div>
          <div class="panel-body stack">
            <div class="kpis">
              <div class="kpi">
                <div id="quotaRemaining" class="kpi-value">-</div>
                <div class="kpi-label">ainda pode enviar</div>
              </div>
              <div class="kpi">
                <div id="dailyQuota" class="kpi-value">-</div>
                <div class="kpi-label">limite de hoje</div>
              </div>
              <div class="kpi">
                <div id="sentCount" class="kpi-value">-</div>
                <div class="kpi-label">já enviados</div>
              </div>
              <div class="kpi">
                <div id="healthScore" class="kpi-value">-</div>
                <div class="kpi-label">saúde do número</div>
              </div>
            </div>
            <div class="toast" id="toast">Tudo pronto.</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Relatório do aquecimento</div>
          </div>
          <div class="panel-body">
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Número</th>
                    <th>Status</th>
                    <th>Limite</th>
                    <th>Enviados</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody id="reportRows">
                  <tr>
                    <td colspan="5" class="muted">Sem dados ainda</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">Resposta técnica</div>
          </div>
          <div class="panel-body">
            <pre id="raw">{}</pre>
          </div>
        </div>
      </section>
    </main>

    <script>
      const $ = (id) => document.getElementById(id);
      const state = {
        numberId: localStorage.getItem("warmup:numberId") || ""
      };

      $("numberId").value = state.numberId;

      const show = (data) => {
        $("raw").textContent = JSON.stringify(data, null, 2);
      };

      const toast = (message) => {
        $("toast").textContent = message;
      };

      const request = async (path, options = {}) => {
        const response = await fetch(path, {
          ...options,
          headers: {
            "content-type": "application/json",
            ...(options.headers || {})
          }
        });
        const body = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(JSON.stringify(body || { status: response.status }));
        }
        return body;
      };

      const setStatusPill = (value) => {
        const pill = $("numberStatus");
        pill.textContent = value || "none";
        pill.className =
          value === "warming"
            ? "status-pill"
            : value === "auto_paused" || value === "paused"
              ? "status-pill danger"
              : "status-pill warn";
      };

      const updateFromStatus = (data) => {
        if (!data || !data.number) return;
        setStatusPill(data.number.status);
        $("quotaRemaining").textContent = data.quotaRemaining ?? "-";
        $("dailyQuota").textContent = data.schedule?.dailyQuota ?? data.number.dailyQuota ?? "-";
        $("sentCount").textContent = data.schedule?.sentCount ?? 0;
      };

      const loadHealth = async () => {
        const id = $("numberId").value.trim();
        if (!id) return null;
        const health = await request("/numbers/" + id + "/health");
        $("healthScore").textContent = health.snapshot?.score ?? "-";
        return health;
      };

      const loadReport = async () => {
        const report = await request("/warmup/report");
        const rows = report.numbers || [];
        $("reportRows").innerHTML =
          rows.length === 0
            ? '<tr><td colspan="5" class="muted">Sem dados ainda</td></tr>'
            : rows
                .map((row) =>
                  [
                    "<tr>",
                    "<td>" + row.phoneNumber + "</td>",
                    "<td>" + row.status + "</td>",
                    "<td>" + (row.latestScheduleQuota ?? row.currentDailyQuota ?? "-") + "</td>",
                    "<td>" + (row.latestSentCount ?? 0) + "</td>",
                    "<td>" + (row.latestHealthScore ?? "-") + "</td>",
                    "</tr>"
                  ].join("")
                )
                .join("");
        return report;
      };

      const refreshAll = async () => {
        const id = $("numberId").value.trim();
        const result = {};
        if (id) {
          result.status = await request("/numbers/" + id + "/status");
          updateFromStatus(result.status);
          result.health = await loadHealth();
        }
        result.report = await loadReport();
        show(result);
        toast("Atualizado.");
      };

      $("createNumber").addEventListener("click", async () => {
        try {
          const created = await request("/numbers", {
            method: "POST",
            body: JSON.stringify({
              phoneNumber: $("phoneNumber").value.trim(),
              displayName: $("displayName").value.trim(),
              webhookUrl: $("webhookUrl").value.trim()
            })
          });
          state.numberId = created.number.id;
          localStorage.setItem("warmup:numberId", state.numberId);
          $("numberId").value = state.numberId;
          show(created);
          toast("Número cadastrado.");
          await refreshAll();
        } catch (error) {
          toast(error.message);
        }
      });

      $("startWarmup").addEventListener("click", async () => {
        try {
          const id = $("numberId").value.trim();
          const recipients = $("recipients").value
            .split(/\r?\n/)
            .map((value) => value.trim())
            .filter(Boolean);
          const started = await request("/numbers/" + id + "/warmup/start", {
            method: "POST",
            body: JSON.stringify({
              recipients,
              template: $("template").value,
              variables: {
                name: $("varName").value,
                company: $("varCompany").value
              }
            })
          });
          show(started);
          toast("Agendado: " + started.scheduledJobs.length + " envio(s).");
          setTimeout(refreshAll, 1500);
        } catch (error) {
          toast(error.message);
        }
      });

      $("pauseWarmup").addEventListener("click", async () => {
        try {
          const id = $("numberId").value.trim();
          const paused = await request("/numbers/" + id + "/warmup/pause", { method: "POST" });
          show(paused);
          toast("Pausado.");
          await refreshAll();
        } catch (error) {
          toast(error.message);
        }
      });

      $("refresh").addEventListener("click", () => {
        refreshAll().catch((error) => toast(error.message));
      });

      $("numberId").addEventListener("change", () => {
        state.numberId = $("numberId").value.trim();
        localStorage.setItem("warmup:numberId", state.numberId);
      });

      request("/healthz")
        .then(() => {
          $("apiState").textContent = "online";
          $("apiState").className = "status-pill";
        })
        .catch(() => {
          $("apiState").textContent = "offline";
          $("apiState").className = "status-pill danger";
        })
        .finally(() => {
          refreshAll().catch(() => loadReport().catch(() => undefined));
        });
    </script>
  </body>
</html>`;

export async function registerDashboardRoute(app: FastifyInstance): Promise<void> {
  app.get('/', async (_request, reply) => {
    reply.type('text/html; charset=utf-8').send(dashboardHtml);
  });
}
