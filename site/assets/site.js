const RELEASES_URL = "https://github.com/albertomosconi/spectrexcel/releases/latest";
const DOWNLOAD_BASE = `${RELEASES_URL}/download`;
const WINDOWS_ASSET = "spectrexcel-windows-x86_64.exe";
const LINUX_ASSET = "SpectrExcel-x86_64.AppImage.tar.gz";

// Release assets resolve under /releases/latest/download/.
function platformName() {
  const value = [
    navigator.userAgentData?.platform,
    navigator.platform,
    navigator.userAgent,
  ].filter(Boolean).join(" ").toLowerCase();
  if (value.includes("win")) return "windows";
  if (value.includes("linux") && !value.includes("android")) return "linux";
  return null;
}

const platform = platformName();
const primaryDownload = document.querySelector("[data-download]");
if (primaryDownload && platform) {
  const asset = platform === "windows" ? WINDOWS_ASSET : LINUX_ASSET;
  primaryDownload.href = `${DOWNLOAD_BASE}/${asset}`;
  primaryDownload.textContent = primaryDownload.dataset[`${platform}Label`];
}

for (const link of document.querySelectorAll("[data-language]")) {
  link.addEventListener("click", () => {
    try { localStorage.setItem("spectrexcel-language", link.dataset.language); }
    catch (_) { /* Navigation remains functional without storage. */ }
  });
}

if (document.documentElement.lang === "en" && location.pathname === "/") {
  try {
    if (localStorage.getItem("spectrexcel-language") === "it") location.replace("/it/");
  } catch (_) { /* English root remains usable without storage. */ }
}
