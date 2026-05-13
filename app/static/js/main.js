document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector(".app-sidebar");
  if (sidebar) {
    sidebar.dataset.ready = "true";
  }
});
