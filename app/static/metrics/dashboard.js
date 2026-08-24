let TOKEN = "";

const METRIC_LABELS = {
  requests_per_minute: "Requests por minuto",
  avg_latency_ms: "Latência média (ms)",
  error_rate_pct: "Taxa de erro (%)",
  tool_calls_per_minute: "Tool calls por minuto",
};

const FORMATTERS = {
  requests_per_minute: (v) => String(v),
  avg_latency_ms: (v) => v.toFixed(1) + " ms",
  error_rate_pct: (v) => v.toFixed(1) + "%",
  tool_calls_per_minute: (v) => String(v),
  status: () => "Online",
};

let selectedMetric = "requests_per_minute";
let chart = null;

function buildChart(labels, values) {
  const ctx = document.getElementById("chart").getContext("2d");

  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = values;
    chart.data.datasets[0].label = METRIC_LABELS[selectedMetric];
    chart.update();
    return;
  }

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: METRIC_LABELS[selectedMetric],
        data: values,
        fill: true,
        borderColor: "#7c3aed",
        backgroundColor: "rgba(124, 58, 237, 0.18)",
        tension: 0.3,
        pointRadius: 2,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#4c1d95" } },
        y: { ticks: { color: "#4c1d95" }, beginAtZero: true },
      },
    },
  });
}

async function refresh() {
  const response = await fetch("/metrics/summary", {
    headers: { "Authorization": "Bearer " + TOKEN },
  });

  if (!response.ok) {
    return;
  }

  const data = await response.json();

  for (const key of Object.keys(FORMATTERS)) {
    const el = document.getElementById("card-" + key);

    if (!el) continue;

    const value = key === "status" ? data.current.status : data.current[key];

    el.textContent = FORMATTERS[key](value);
  }

  const serie = data.series[selectedMetric].slice(-5);
  const labels = serie.map((p) => p.minute.slice(11, 16));
  const values = serie.map((p) => p.value);

  document.getElementById("chart-label").textContent =
    METRIC_LABELS[selectedMetric] + " — últimos 5 min";

  buildChart(labels, values);
}

function formatarUsd(valor) {
  return "US$ " + Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

async function refreshCost() {
  const requestsPerUser = document.getElementById("input-requests-per-user").value || 0;
  const valuePerResolution = document.getElementById("input-value-per-resolution").value || 0;

  const params = new URLSearchParams({
    requests_per_user_per_week: requestsPerUser,
    value_per_resolution_usd: valuePerResolution,
  });

  const response = await fetch("/metrics/cost?" + params.toString(), {
    headers: { "Authorization": "Bearer " + TOKEN },
  });

  if (!response.ok) {
    return;
  }

  const data = await response.json();

  document.getElementById("cost-100").textContent = formatarUsd(data.estimated_weekly_cost_100_users_usd);
  document.getElementById("cost-1000").textContent = formatarUsd(data.estimated_weekly_cost_1000_users_usd);
  document.getElementById("cost-per-resolution").textContent =
    data.cost_per_resolution_usd === null ? "-" : formatarUsd(data.cost_per_resolution_usd);
  document.getElementById("cost-roi").textContent =
    data.roi_pct === null ? "informe o valor por resolução" : data.roi_pct.toFixed(1) + "%";
  document.getElementById("cost-total").textContent = formatarUsd(data.total_cost_usd);
  document.getElementById("cost-tokens").textContent =
    (data.total_input_tokens + data.total_output_tokens).toLocaleString("pt-BR");
}

document.getElementById("input-requests-per-user").addEventListener("change", refreshCost);
document.getElementById("input-value-per-resolution").addEventListener("change", refreshCost);

document.querySelectorAll(".card[data-metric]").forEach((card) => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".card[data-metric]").forEach((c) => c.classList.remove("active"));
    card.classList.add("active");
    selectedMetric = card.dataset.metric;
    refresh();
  });
});

async function chaveValida(chave) {
  const response = await fetch("/metrics/summary", {
    headers: { "Authorization": "Bearer " + chave },
  });

  return response.ok;
}

async function autenticar() {
  let mensagem = "Informe a chave de observabilidade:";
  let chave = window.prompt(mensagem);

  while (chave !== null) {
    if (await chaveValida(chave)) {
      TOKEN = chave;

      document.getElementById("dashboard-content").style.display = "block";

      refresh();
      refreshCost();
      setInterval(refresh, 5000);

      return;
    }

    mensagem = "Chave inválida. Informe a chave de observabilidade:";
    chave = window.prompt(mensagem);
  }
}

autenticar();
