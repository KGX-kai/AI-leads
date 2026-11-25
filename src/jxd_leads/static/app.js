"use strict";
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.hasAttribute("data-back")) history.back();
  if (button.dataset.copy) {
    const field = document.getElementById(button.dataset.copy);
    try { await navigator.clipboard.writeText(field.value); toast("已复制，请核对目标位置后粘贴。"); }
    catch { field.focus(); field.select(); toast("请按 ⌘C 复制选中的文本。"); }
  }
  if (button.dataset.reveal) {
    const target = document.getElementById("contact-" + button.dataset.reveal);
    try {
      const response = await fetch("/api/v1/contacts/" + button.dataset.reveal + "/reveal", {method:"POST", headers:{"X-CSRF-Token":document.querySelector('meta[name="csrf-token"]').content}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "无法查看，请刷新页面");
      target.textContent = data.name + " · " + data.channel;
      setTimeout(() => {target.textContent="";}, 30000);
    } catch (error) { toast(error.message); }
  }
});
document.addEventListener("submit", (event) => {
  const message = event.target.dataset.confirm;
  if (message && !confirm(message)) event.preventDefault();
});
document.addEventListener("htmx:responseError", () => toast("筛选请求失败，请刷新后重试。"));
function toast(message) {const target=document.getElementById("toast");target.textContent=message;target.classList.add("visible");setTimeout(()=>target.classList.remove("visible"),4500);}
