const INTERVALO_MS = 20000;
const CHAVE_SESSAO = "ceris_api_key";
const MAX_PONTOS = 40;

const COR_MEMORIA = "#7c3aed";
const COR_CPU = "#16a34a";

const historico = [];
let grafico = null;
let temporizador = null;

function elemento(id) {
  return document.getElementById(id);
}

function duracao(segundos) {
  if (segundos < 60) return Math.round(segundos) + "s";
  if (segundos < 3600) return Math.floor(segundos / 60) + "min";
  if (segundos < 86400) return Math.floor(segundos / 3600) + "h";
  return Math.floor(segundos / 86400) + "d";
}

function lerChaveSalva() {
  try {
    return sessionStorage.getItem(CHAVE_SESSAO) || "";
  } catch (e) {
    return "";
  }
}

function salvarChave(chave) {
  try {
    sessionStorage.setItem(CHAVE_SESSAO, chave);
  } catch (e) {
    return;
  }
}

function limparChave() {
  try {
    sessionStorage.removeItem(CHAVE_SESSAO);
  } catch (e) {
    return;
  }
}

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

function desenharGrafico() {
  const canvas = elemento("chart");
  if (!canvas || !window.Chart || !historico.length) return;

  const rotulos = historico.map(function (h) {
    return new Date(h.verificado_em).toLocaleTimeString("pt-BR");
  });

  const memoria = historico.map(function (h) {
    return h.recursos ? h.recursos.memoria_mb : null;
  });

  const cpu = historico.map(function (h) {
    return h.recursos ? h.recursos.cpu_pct : null;
  });

  if (grafico) {
    grafico.data.labels = rotulos;
    grafico.data.datasets[0].data = memoria;
    grafico.data.datasets[1].data = cpu;
    grafico.update();
    return;
  }

  grafico = new Chart(canvas, {
    type: "line",
    data: {
      labels: rotulos,
      datasets: [
        {
          label: "Memória (MB)",
          data: memoria,
          borderColor: COR_MEMORIA,
          backgroundColor: COR_MEMORIA + "22",
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
          yAxisID: "y",
        },
        {
          label: "CPU (%)",
          data: cpu,
          borderColor: COR_CPU,
          backgroundColor: COR_CPU + "22",
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 12, font: { size: 11 } } },
      },
      scales: {
        y: {
          position: "left",
          beginAtZero: true,
          title: { display: true, text: "MB" },
          grid: { color: "#f3f4f6" },
        },
        y1: {
          position: "right",
          beginAtZero: true,
          suggestedMax: 100,
          title: { display: true, text: "%" },
          grid: { drawOnChartArea: false },
        },
        x: { grid: { display: false } },
      },
    },
  });
}

function renderizar(dados) {
  const classe = { saudavel: "ok", degradado: "alerta", indisponivel: "erro" }[dados.estado] || "alerta";

  const estado = elemento("estado");
  estado.textContent = dados.estado;
  estado.className = "pill " + classe;

  elemento("falhas").textContent = dados.falhas
    ? dados.falhas + " de " + dados.total + " fora do ar"
    : dados.total + " serviços online";

  const recursos = dados.recursos || {};

  elemento("memoria").textContent = (recursos.memoria_mb || 0) + " MB";
  elemento("memoria-hint").textContent = (recursos.memoria_pct || 0) + "% da máquina";

  elemento("cpu").textContent = (recursos.cpu_pct || 0) + "%";
  elemento("cpu-hint").textContent = (recursos.threads || 0) + " threads";

  elemento("uptime").textContent = duracao(dados.uptime_segundos);
  elemento("momento").textContent = new Date(dados.verificado_em).toLocaleTimeString("pt-BR");

  elemento("lista").innerHTML = dados.dependencias
    .map(function (dep) {
      const online = dep.status === "ok";
      const detalhe = online ? "" : '<div class="dep-det">' + escapar(dep.detalhe) + "</div>";

      return (
        '<div class="dep">' +
        '<div class="bola ' + (online ? "ok" : "erro") + '"></div>' +
        '<div class="dep-nome">' + escapar(dep.nome) + "</div>" +
        detalhe +
        '<div class="dep-estado ' + (online ? "ok" : "erro") + '">' +
        (online ? "online" : "offline") +
        "</div></div>"
      );
    })
    .join("");

  desenharGrafico();
}

function mostrarFalha(titulo, detalhe) {
  const estado = elemento("estado");
  estado.textContent = titulo;
  estado.className = "pill erro";
  elemento("falhas").textContent = detalhe;
  elemento("lista").innerHTML = "";
}

function aguardandoChave() {
  const estado = elemento("estado");
  estado.textContent = "aguardando chave";
  estado.className = "pill alerta";
  elemento("falhas").textContent = "informe a X-API-Key e clique em Verificar";
  elemento("lista").innerHTML = "";
}

function pararPolling() {
  if (temporizador) {
    clearInterval(temporizador);
    temporizador = null;
  }
}

function iniciarPolling() {
  pararPolling();
  temporizador = setInterval(carregar, INTERVALO_MS);
}

async function carregar() {
  const chave = elemento("apikey").value.trim();

  if (!chave) {
    pararPolling();
    aguardandoChave();
    return;
  }

  try {
    const resposta = await fetch("/health/dependencies", {
      headers: { "X-API-Key": chave },
    });

    if (resposta.status === 401) {
      pararPolling();
      limparChave();

      const estado = elemento("estado");
      estado.textContent = "chave inválida";
      estado.className = "pill erro";
      elemento("falhas").textContent = "confira a X-API-Key e tente de novo";
      elemento("lista").innerHTML = "";
      return;
    }

    if (!resposta.ok) {
      throw new Error("HTTP " + resposta.status);
    }

    const dados = await resposta.json();

    salvarChave(chave);
    iniciarPolling();

    historico.push(dados);
    if (historico.length > MAX_PONTOS) {
      historico.shift();
    }

    renderizar(dados);
  } catch (erro) {
    mostrarFalha("API inalcançável", String(erro.message || erro));
  }
}

async function exportarRelatorio() {
  const chave = elemento("apikey").value.trim();
  const botao = elemento("relatorio");

  if (!chave) {
    aguardandoChave();
    return;
  }

  const rotulo = botao.textContent;
  botao.disabled = true;
  botao.textContent = "Gerando...";

  const parametros = new URLSearchParams({
    dias: elemento("dias").value,
    mensagens_semana: elemento("mensagens-semana").value || "10",
    economia_mensal_brl: elemento("economia").value || "0",
  });

  let endereco = null;

  try {
    const resposta = await fetch("/health/report?" + parametros.toString(), {
      headers: { "X-API-Key": chave },
    });

    if (!resposta.ok) {
      throw new Error("HTTP " + resposta.status);
    }

    const blob = await resposta.blob();
    endereco = URL.createObjectURL(blob);

    if (!window.open(endereco, "_blank")) {
      const link = document.createElement("a");
      link.href = endereco;
      link.download = "relatorio-ceris.html";
      link.click();
    }
  } catch (erro) {
    mostrarFalha("falha ao gerar relatório", String(erro.message || erro));
  } finally {
    botao.disabled = false;
    botao.textContent = rotulo;

    if (endereco) {
      setTimeout(function () { URL.revokeObjectURL(endereco); }, 60000);
    }
  }
}

function iniciar() {
  const salva = lerChaveSalva();

  elemento("verificar").addEventListener("click", carregar);
  elemento("relatorio").addEventListener("click", exportarRelatorio);

  elemento("apikey").addEventListener("keydown", function (evento) {
    if (evento.key === "Enter") {
      carregar();
    }
  });

  if (salva) {
    elemento("apikey").value = salva;
    carregar();
    return;
  }

  aguardandoChave();
}

document.addEventListener("DOMContentLoaded", iniciar);
