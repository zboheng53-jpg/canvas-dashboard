(() => {
  const candidateInputs = document.querySelectorAll('input[name="action-candidate"]');
  const candidateCards = document.querySelectorAll("[data-candidate]");
  const modalBackdrop = document.querySelector("[data-modal-backdrop]");
  const modalOpen = document.querySelector("[data-modal-open]");
  const modalCloseButtons = document.querySelectorAll("[data-modal-close]");
  const passwordToggle = document.querySelector("[data-password-toggle]");
  const passwordInput = document.querySelector("#lab-password");
  const navItems = Array.from(document.querySelectorAll(".lab-nav-item"));
  let modalReturnFocus = null;

  candidateInputs.forEach((input) => {
    input.addEventListener("change", () => {
      candidateCards.forEach((card) => {
        const selected = card.contains(input);
        card.dataset.selected = selected ? "true" : "false";
      });
    });
  });

  const closeModal = () => {
    if (!modalBackdrop || modalBackdrop.hidden) return;
    modalBackdrop.hidden = true;
    document.body.classList.remove("lab-modal-open");
    modalReturnFocus?.focus();
  };

  modalOpen?.addEventListener("click", () => {
    if (!modalBackdrop) return;
    modalReturnFocus = document.activeElement;
    modalBackdrop.hidden = false;
    document.body.classList.add("lab-modal-open");
    modalBackdrop.querySelector("input")?.focus();
  });

  modalCloseButtons.forEach((button) => button.addEventListener("click", closeModal));
  modalBackdrop?.addEventListener("click", (event) => {
    if (event.target === modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  passwordToggle?.addEventListener("click", () => {
    if (!passwordInput) return;
    const isHidden = passwordInput.type === "password";
    passwordInput.type = isHidden ? "text" : "password";
    passwordToggle.textContent = isHidden ? "隐藏" : "显示";
    passwordToggle.setAttribute("aria-label", isHidden ? "隐藏密码" : "显示密码");
  });

  navItems.forEach((item) => {
    item.addEventListener("click", () => {
      navItems.forEach((navItem) => navItem.classList.toggle("is-selected", navItem === item));
    });
  });
})();
