const form = document.querySelector("#upload-form");
const input = document.querySelector("#file");
const dropZone = document.querySelector("#drop-zone");
const selectedFile = document.querySelector("#selected-file");
const submitButton = document.querySelector("#submit-button");
const buttonLabel = document.querySelector("#button-label");

if (form && input && dropZone && selectedFile && submitButton && buttonLabel) {
  const supportedExtensions = new Set(["jpg", "jpeg", "png", "mp4", "avi", "mov", "mkv"]);
  const maxSize = 16 * 1024 * 1024;

  function updateSelection(file) {
    selectedFile.textContent = file ? file.name : "No file selected";
    selectedFile.classList.toggle("has-error", Boolean(file && file.size > maxSize));
  }

  input.addEventListener("change", () => updateSelection(input.files[0]));

  for (const eventName of ["dragenter", "dragover"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
  }

  for (const eventName of ["dragleave", "drop"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
    });
  }

  dropZone.addEventListener("drop", (event) => {
    const [file] = event.dataTransfer.files;
    if (!file) return;

    const extension = file.name.split(".").pop().toLowerCase();
    if (!supportedExtensions.has(extension)) {
      input.value = "";
      selectedFile.textContent = "Unsupported file type. Choose an image or video listed above.";
      selectedFile.classList.add("has-error");
      return;
    }

    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    updateSelection(file);
  });

  form.addEventListener("submit", (event) => {
    const file = input.files[0];
    if (!file) return;
    const extension = file.name.split(".").pop().toLowerCase();
    if (!supportedExtensions.has(extension) || file.size > maxSize) {
      event.preventDefault();
      selectedFile.textContent = file.size > maxSize
        ? "That file is larger than 16 MB."
        : "Unsupported file type. Choose an image or video listed above.";
      selectedFile.classList.add("has-error");
      return;
    }

    submitButton.disabled = true;
    buttonLabel.textContent = "Inspecting file…";
  });
}
