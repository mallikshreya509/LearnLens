// Where the backend lives. Edit this when you deploy.
//   ""                      same origin: the backend is also serving this folder (default)
//   "http://localhost:8000" this folder runs on its own dev server (port 5173)
window.LEARNLENS_API =
  window.LEARNLENS_API ?? (location.port === "5173" ? "http://localhost:8000" : "");
