// Progressive enhancement only; every page works without JavaScript.
document.addEventListener("DOMContentLoaded", function () {
  // Tabs on the scan form.
  document.querySelectorAll("[data-tabs]").forEach(function (group) {
    var buttons = group.querySelectorAll("[role=tab]");
    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        buttons.forEach(function (b) {
          var selected = b === button;
          b.setAttribute("aria-selected", selected ? "true" : "false");
          var panel = document.getElementById(b.getAttribute("aria-controls"));
          if (panel) { panel.hidden = !selected; }
        });
      });
    });
  });
});
