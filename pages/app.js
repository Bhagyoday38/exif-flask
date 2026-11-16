"use strict";

const fileInput = document.querySelector("#files");
const dropZone = document.querySelector("#drop-zone");
const selectionSummary = document.querySelector("#selected-file");
const selectionError = document.querySelector("#selection-error");
const resultList = document.querySelector("#results-list");
const emptyState = document.querySelector("#empty-state");
const fileCount = document.querySelector("#file-count");
const entries = new Map();
const supportedImages = new Set(["jpg", "jpeg", "png"]);
const supportedVideos = new Set(["mp4", "mov", "webm"]);
const maxFiles = 10;
const maxFileSize = 16 * 1024 * 1024;
const maxTotalSize = 64 * 1024 * 1024;
let totalBytes = 0;
let nextEntryId = 0;

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function formatBytes(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function updateLibrary() {
  const count = entries.size;
  fileCount.textContent = `${count} ${count === 1 ? "file" : "files"}`;
  selectionSummary.textContent = count
    ? `${count} ${count === 1 ? "file" : "files"} in this tab · ${formatBytes(totalBytes)}`
    : "Select up to 10 files · 16 MB each";
  emptyState.hidden = count > 0;
}

function addTable(container, rows, label) {
  const section = makeElement("section");
  section.setAttribute("aria-label", label);
  const heading = makeElement("div", "data-heading");
  heading.append(makeElement("h4", "", label));
  const tableWrap = makeElement("div", "table-wrap");
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerRow.append(makeElement("th", "", "Tag"), makeElement("th", "", "Value"));
  head.append(headerRow);
  table.append(head);
  const body = document.createElement("tbody");

  for (const [name, value] of rows) {
    const row = document.createElement("tr");
    const key = makeElement("th", "", name);
    key.scope = "row";
    row.append(key, makeElement("td", "", value));
    body.append(row);
  }
  table.append(body);
  tableWrap.append(table);
  section.append(heading, tableWrap);
  container.append(section);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return "Unknown";
  const totalSeconds = Math.floor(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`
    : `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function addGpsCard(container, gps) {
  if (!gps) return;
  const card = makeElement("section", "gps-card");
  card.setAttribute("aria-label", "GPS coordinates");
  const details = document.createElement("div");
  details.append(
    makeElement("h4", "", "Location found"),
    makeElement(
      "p",
      "coordinates",
      `${gps.latitude.toFixed(6)}, ${gps.longitude.toFixed(6)}`,
    ),
  );
  const mapLink = makeElement("a", "map-link", "Open map ↗");
  mapLink.href = `https://www.google.com/maps?q=${gps.latitude},${gps.longitude}`;
  mapLink.target = "_blank";
  mapLink.rel = "noopener noreferrer";
  card.append(details, mapLink);
  container.append(card);
}

function addFile(file) {
  const extension = file.name.split(".").pop().toLowerCase();
  const isImage = supportedImages.has(extension);
  if (!isImage && !supportedVideos.has(extension)) {
    return `${file.name}: choose a JPEG, PNG, MP4, MOV, or WebM file.`;
  }
  if (file.size > maxFileSize) {
    return `${file.name}: each file must be 16 MB or smaller.`;
  }
  if (entries.size >= maxFiles) {
    return `Choose no more than ${maxFiles} files at a time.`;
  }
  if (totalBytes + file.size > maxTotalSize) {
    return "The combined file size must be 64 MB or smaller.";
  }

  const id = nextEntryId++;
  const objectUrl = URL.createObjectURL(file);
  const card = makeElement("article", "result-item");
  const heading = makeElement("div", "result-heading");
  const identity = makeElement("div", "file-identity");
  const kind = makeElement("span", "file-kind", isImage ? "IMG" : "VID");
  kind.setAttribute("aria-hidden", "true");
  const fileInfo = document.createElement("div");
  fileInfo.append(
    makeElement("h3", "", file.name),
    makeElement(
      "p",
      "",
      `${isImage ? "Image" : "Video"} · ${formatBytes(file.size)}`,
    ),
  );
  identity.append(kind, fileInfo);

  const removeButton = makeElement("button", "delete-button", "Remove");
  removeButton.type = "button";
  removeButton.setAttribute("aria-label", `Remove ${file.name}`);
  removeButton.addEventListener("click", () => {
    URL.revokeObjectURL(objectUrl);
    card.remove();
    entries.delete(id);
    totalBytes -= file.size;
    updateLibrary();
  });
  heading.append(identity, removeButton);

  const content = makeElement("div", "result-content");
  const preview = makeElement("figure", "preview-card");
  preview.setAttribute("aria-label", `Preview of ${file.name}`);
  const metadata = makeElement("div", "metadata");
  const status = makeElement("p", "metadata-empty", "Reading file details…");
  status.setAttribute("role", "status");
  content.append(preview, metadata);
  card.append(heading, content);
  resultList.prepend(card);
  entries.set(id, { file, objectUrl });
  totalBytes += file.size;
  updateLibrary();

  if (isImage) {
    const image = document.createElement("img");
    image.src = objectUrl;
    image.alt = `Preview of ${file.name}`;
    image.loading = "lazy";
    image.addEventListener("error", () => {
      status.textContent = "This image could not be opened by your browser.";
    });
    preview.append(image);
    metadata.append(status);
    file.arrayBuffer()
      .then((buffer) => {
        if (!entries.has(id)) return;
        const result = window.MediaMetadata.readExif(new Uint8Array(buffer));
        if (result && result.entries.length) {
          metadata.replaceChildren();
          addTable(
            metadata,
            result.entries.map((entry) => [entry.name, entry.value]),
            "Image details",
          );
          addGpsCard(metadata, result.gps);
        } else {
          status.textContent = "No readable EXIF metadata was found in this image.";
        }
      })
      .catch(() => {
        status.textContent = "The image details could not be read.";
      });
  } else {
    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.addEventListener("loadedmetadata", () => {
      metadata.replaceChildren();
      const details = makeElement("section");
      const title = makeElement("div", "data-heading");
      title.append(makeElement("h4", "", "Video details"));
      const values = makeElement("dl", "video-details");
      const resolution = document.createElement("div");
      resolution.append(
        makeElement("dt", "", "Resolution"),
        makeElement("dd", "", `${video.videoWidth} × ${video.videoHeight}`),
      );
      const duration = document.createElement("div");
      duration.append(
        makeElement("dt", "", "Duration"),
        makeElement("dd", "", formatDuration(video.duration)),
      );
      values.append(resolution, duration);
      details.append(title, values);
      metadata.append(details);
    });
    video.addEventListener("error", () => {
      status.textContent =
        "This video format is not supported by your browser. Try an MP4, MOV, or WebM file.";
    });
    video.src = objectUrl;
    preview.append(video);
    metadata.append(status);
  }
  return null;
}

function addFiles(files) {
  const errors = [];
  for (const file of files) {
    const error = addFile(file);
    if (error) errors.push(error);
  }
  selectionError.textContent = errors.join(" ");
  selectionError.hidden = errors.length === 0;
  updateLibrary();
}

fileInput.addEventListener("change", () => {
  addFiles(Array.from(fileInput.files));
  fileInput.value = "";
});

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });
}

dropZone.addEventListener("dragleave", (event) => {
  if (!dropZone.contains(event.relatedTarget)) dropZone.classList.remove("is-dragging");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragging");
  addFiles(Array.from(event.dataTransfer.files));
});

updateLibrary();
