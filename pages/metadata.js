(function (root) {
  "use strict";

  const TAG_NAMES = {
    0x010e: "ImageDescription",
    0x010f: "Make",
    0x0110: "Model",
    0x0112: "Orientation",
    0x0131: "Software",
    0x0132: "DateTime",
    0x829a: "ExposureTime",
    0x829d: "FNumber",
    0x8769: "ExifIFDPointer",
    0x8825: "GPSInfo",
    0x8827: "ISO",
    0x9003: "DateTimeOriginal",
    0x920a: "FocalLength",
    0xa002: "PixelXDimension",
    0xa003: "PixelYDimension",
  };
  const GPS_TAG_NAMES = {
    1: "GPSLatitudeRef",
    2: "GPSLatitude",
    3: "GPSLongitudeRef",
    4: "GPSLongitude",
    5: "GPSAltitudeRef",
    6: "GPSAltitude",
    7: "GPSTimeStamp",
    29: "GPSDateStamp",
  };
  const TYPE_SIZES = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 8: 2, 9: 4, 10: 8 };
  const MAX_TAG_VALUES = 4096;

  function findExifPayload(bytes) {
    if (
      bytes.length >= 8 &&
      bytes[0] === 0x89 &&
      bytes[1] === 0x50 &&
      bytes[2] === 0x4e &&
      bytes[3] === 0x47
    ) {
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      let offset = 8;
      while (offset + 12 <= bytes.length) {
        const length = view.getUint32(offset);
        const dataStart = offset + 8;
        const dataEnd = dataStart + length;
        if (dataEnd + 4 > bytes.length) return null;
        const type = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8));
        if (type === "eXIf") return { start: dataStart, end: dataEnd };
        if (type === "IEND") break;
        offset = dataEnd + 4;
      }
      return null;
    }

    if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;
    let offset = 2;
    while (offset < bytes.length) {
      if (bytes[offset] !== 0xff) return null;
      while (bytes[offset] === 0xff) offset += 1;
      const marker = bytes[offset];
      offset += 1;
      if (marker === 0xd9 || marker === 0xda) break;
      if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
      if (offset + 2 > bytes.length) return null;
      const length = (bytes[offset] << 8) | bytes[offset + 1];
      const dataStart = offset + 2;
      const dataEnd = offset + length;
      if (length < 2 || dataEnd > bytes.length) return null;
      if (
        marker === 0xe1 &&
        dataEnd - dataStart >= 6 &&
        String.fromCharCode(...bytes.subarray(dataStart, dataStart + 6)) === "Exif\u0000\u0000"
      ) {
        return { start: dataStart + 6, end: dataEnd };
      }
      offset = dataEnd;
    }
    return null;
  }

  function readTiff(bytes, tiffStart, tiffEnd) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const inBounds = (offset, size) =>
      Number.isSafeInteger(offset) &&
      Number.isSafeInteger(size) &&
      offset >= tiffStart &&
      size >= 0 &&
      offset + size <= tiffEnd;
    if (!inBounds(tiffStart, 8)) return null;

    const order = String.fromCharCode(bytes[tiffStart], bytes[tiffStart + 1]);
    if (order !== "II" && order !== "MM") return null;
    const littleEndian = order === "II";
    if (view.getUint16(tiffStart + 2, littleEndian) !== 42) return null;

    function readIfd(relativeOffset) {
      const offset = tiffStart + relativeOffset;
      if (!inBounds(offset, 2)) return null;
      const count = view.getUint16(offset, littleEndian);
      if (count > MAX_TAG_VALUES || !inBounds(offset + 2, count * 12 + 4)) return null;
      const values = new Map();

      for (let index = 0; index < count; index += 1) {
        const entry = offset + 2 + index * 12;
        const tag = view.getUint16(entry, littleEndian);
        const type = view.getUint16(entry + 2, littleEndian);
        const valueCount = view.getUint32(entry + 4, littleEndian);
        const typeSize = TYPE_SIZES[type];
        if (!typeSize || valueCount > MAX_TAG_VALUES) continue;

        const byteLength = typeSize * valueCount;
        const valueOffset =
          byteLength <= 4
            ? entry + 8
            : tiffStart + view.getUint32(entry + 8, littleEndian);
        if (!inBounds(valueOffset, byteLength)) return null;

        const items = [];
        for (let item = 0; item < valueCount; item += 1) {
          const position = valueOffset + item * typeSize;
          if (type === 1 || type === 7) items.push(view.getUint8(position));
          else if (type === 2) items.push(view.getUint8(position));
          else if (type === 3) items.push(view.getUint16(position, littleEndian));
          else if (type === 4) items.push(view.getUint32(position, littleEndian));
          else if (type === 5 || type === 10) {
            const numerator =
              type === 5
                ? view.getUint32(position, littleEndian)
                : view.getInt32(position, littleEndian);
            const denominator =
              type === 5
                ? view.getUint32(position + 4, littleEndian)
                : view.getInt32(position + 4, littleEndian);
            items.push(denominator === 0 ? null : numerator / denominator);
          } else if (type === 8) items.push(view.getInt16(position, littleEndian));
          else if (type === 9) items.push(view.getInt32(position, littleEndian));
        }

        if (type === 2) {
          const text = String.fromCharCode(...items).replace(/\0+$/, "").trim();
          values.set(tag, text);
        } else {
          values.set(tag, items.length === 1 ? items[0] : items);
        }
      }
      return values;
    }

    const firstIfd = readIfd(view.getUint32(tiffStart + 4, littleEndian));
    if (!firstIfd) return null;
    const exifPointer = firstIfd.get(0x8769);
    const gpsPointer = firstIfd.get(0x8825);
    const exifIfd = Number.isInteger(exifPointer) ? readIfd(exifPointer) : new Map();
    const gpsIfd = Number.isInteger(gpsPointer) ? readIfd(gpsPointer) : new Map();
    if (!exifIfd || !gpsIfd) return null;

    const entries = [];
    for (const [tag, value] of [...firstIfd, ...exifIfd]) {
      if (tag === 0x8769 || tag === 0x8825 || value === "") continue;
      entries.push({
        name: TAG_NAMES[tag] || `Tag 0x${tag.toString(16).padStart(4, "0")}`,
        value: Array.isArray(value) ? value.join(", ") : String(value),
      });
    }
    for (const [tag, value] of gpsIfd) {
      const name = GPS_TAG_NAMES[tag] || `GPS tag 0x${tag.toString(16)}`;
      entries.push({
        name,
        value: Array.isArray(value) ? value.join(", ") : String(value),
      });
    }

    function coordinate(value, reference, negativeReference, maximum) {
      if (
        !Array.isArray(value) ||
        value.length !== 3 ||
        value.some(
          (part) => typeof part !== "number" || !Number.isFinite(part) || part < 0,
        ) ||
        value[1] >= 60 ||
        value[2] >= 60 ||
        value[0] > maximum ||
        (value[0] === maximum && (value[1] !== 0 || value[2] !== 0))
      ) {
        return null;
      }
      const decimal = value[0] + value[1] / 60 + value[2] / 3600;
      const positiveReference = negativeReference === "S" ? "N" : "E";
      if (reference === negativeReference) return -decimal;
      return reference === positiveReference ? decimal : null;
    }

    const latitude = coordinate(gpsIfd.get(2), gpsIfd.get(1), "S", 90);
    const longitude = coordinate(gpsIfd.get(4), gpsIfd.get(3), "W", 180);
    const gps = latitude === null || longitude === null ? null : { latitude, longitude };
    return entries.length ? { entries, gps } : null;
  }

  function readExif(input) {
    const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
    const payload = findExifPayload(bytes);
    return payload ? readTiff(bytes, payload.start, payload.end) : null;
  }

  const api = Object.freeze({ readExif });
  root.MediaMetadata = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
