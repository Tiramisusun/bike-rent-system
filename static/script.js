const output = document.getElementById("output");

async function loadJson(url) {
  output.textContent = "Loading...";
  try {
    const res = await fetch(url);
    const data = await res.json();
    output.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    output.textContent = "Error: " + e;
  }
}

document.getElementById("btnBikes").addEventListener("click", () => loadJson("/api/bikes"));
document.getElementById("btnWeather").addEventListener("click", () => loadJson("/api/weather"));
