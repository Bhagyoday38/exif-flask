const form = document.querySelector("#upload-form");
const input = document.querySelector("#files");
const dropZone = document.querySelector("#drop-zone");
const selectedFile = document.querySelector("#selected-file");
const selectedFiles = document.querySelector("#selected-files");
const selectionError = document.querySelector("#selection-error");
const submitButton = document.querySelector("#submit-button");
const buttonLabel = document.querySelector("#button-label");

if (
  form &&
  input &&
  dropZone &&
  selectedFile &&
  selectedFiles &&
  selectionError &&
  submitButton &&
  buttonLabel
) {
  const supportedExtensions = new Set([
    "jpg",
    "jpeg",
    "png",
    "mp4",
    "avi",
    "mov",
    "mkv",
  ]);
  const maxFiles = Number(form.dataset.maxFiles);
  const maxFileSize = Number(form.dataset.maxFileSize);
  const maxTotalSize = Number(form.dataset.maxTotalSize);

  function formatBytes(bytes) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function updateSelection() {
    const files = Array.from(input.files);
    const errors = [];
    const totalSize = files.reduce((total, file) => total + file.size, 0);

    if (files.length > maxFiles) {
      errors.push(`Choose no more than ${maxFiles} files.`);
    }
    if (totalSize > maxTotalSize) {
      errors.push("The combined file size must be under 64 MB.");
    }
    for (const file of files) {
      const extension = file.name.split(".").pop().toLowerCase();
      if (!supportedExtensions.has(extension)) {
        errors.push(`${file.name}: unsupported file type.`);
      } else if (file.size > maxFileSize) {
        errors.push(`${file.name}: each file must be smaller than 16 MB.`);
      }
    }

    selectedFiles.replaceChildren();
    for (const file of files) {
      const item = document.createElement("li");
      item.textContent = `${file.name} · ${formatBytes(file.size)}`;
      selectedFiles.append(item);
    }

    selectedFile.textContent = files.length
      ? `${files.length} ${files.length === 1 ? "file" : "files"} selected`
      : "Select up to 10 files · 16 MB each";
    selectionError.textContent = errors.join(" ");
    selectionError.hidden = errors.length === 0;
    submitButton.disabled = files.length === 0 || errors.length > 0;
    buttonLabel.textContent = files.length
      ? `Inspect ${files.length} ${files.length === 1 ? "file" : "files"}`
      : "Choose files to inspect";
  }

  input.addEventListener("change", updateSelection);

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
    const droppedFiles = Array.from(event.dataTransfer.files);
    if (droppedFiles.length === 0) return;

    const transfer = new DataTransfer();
    for (const file of [...input.files, ...droppedFiles]) {
      transfer.items.add(file);
    }
    input.files = transfer.files;
    updateSelection();
  });

  form.addEventListener("submit", (event) => {
    const files = Array.from(input.files);
    if (submitButton.disabled || files.length === 0) {
      event.preventDefault();
      return;
    }

    submitButton.disabled = true;
    buttonLabel.textContent = `Inspecting ${files.length} ${
      files.length === 1 ? "file" : "files"
    }…`;
  });

  updateSelection();
}
