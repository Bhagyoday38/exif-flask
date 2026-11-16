const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readExif } = require("../pages/metadata.js");

function makeExifTiff() {
  const tiff = Buffer.alloc(152);
  tiff.write("II", 0);
  tiff.writeUInt16LE(42, 2);
  tiff.writeUInt32LE(8, 4);
  tiff.writeUInt16LE(2, 8);

  tiff.writeUInt16LE(0x010f, 10);
  tiff.writeUInt16LE(2, 12);
  tiff.writeUInt32LE(5, 14);
  tiff.writeUInt32LE(44, 18);

  tiff.writeUInt16LE(0x8825, 22);
  tiff.writeUInt16LE(4, 24);
  tiff.writeUInt32LE(1, 26);
  tiff.writeUInt32LE(50, 30);

  tiff.writeUInt32LE(0, 34);
  tiff.write("Acme\0", 44, "ascii");
  tiff.writeUInt16LE(4, 50);

  const gpsEntries = [
    [1, 2, 2, "N\0"],
    [2, 5, 3, 104],
    [3, 2, 2, "W\0"],
    [4, 5, 3, 128],
  ];
  gpsEntries.forEach(([tag, type, count, value], index) => {
    const offset = 52 + index * 12;
    tiff.writeUInt16LE(tag, offset);
    tiff.writeUInt16LE(type, offset + 2);
    tiff.writeUInt32LE(count, offset + 4);
    if (typeof value === "string") {
      tiff.write(value, offset + 8, "ascii");
    } else {
      tiff.writeUInt32LE(value, offset + 8);
    }
  });
  tiff.writeUInt32LE(0, 100);

  [[37, 1], [30, 1], [0, 1], [122, 1], [15, 1], [0, 1]].forEach(
    ([numerator, denominator], index) => {
      tiff.writeUInt32LE(numerator, 104 + index * 8);
      tiff.writeUInt32LE(denominator, 108 + index * 8);
    },
  );
  return tiff;
}

function makeJpegWithExif(tiff) {
  const payload = Buffer.concat([Buffer.from("Exif\0\0", "ascii"), tiff]);
  const segment = Buffer.alloc(payload.length + 4);
  segment[0] = 0xff;
  segment[1] = 0xe1;
  segment.writeUInt16BE(payload.length + 2, 2);
  payload.copy(segment, 4);
  return Buffer.concat([Buffer.from([0xff, 0xd8]), segment, Buffer.from([0xff, 0xd9])]);
}

function makePngWithExif(tiff) {
  const chunk = Buffer.alloc(tiff.length + 12);
  chunk.writeUInt32BE(tiff.length, 0);
  chunk.write("eXIf", 4, "ascii");
  tiff.copy(chunk, 8);
  const end = Buffer.alloc(12);
  end.write("IEND", 4, "ascii");
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk,
    end,
  ]);
}

test("reads EXIF tags and signed GPS coordinates from JPEG", () => {
  const metadata = readExif(makeJpegWithExif(makeExifTiff()));

  assert.equal(metadata.entries.find((entry) => entry.name === "Make").value, "Acme");
  assert.deepEqual(metadata.gps, { latitude: 37.5, longitude: -122.25 });
});

test("reads EXIF metadata from PNG eXIf chunks", () => {
  const metadata = readExif(makePngWithExif(makeExifTiff()));

  assert.equal(metadata.entries.find((entry) => entry.name === "Make").value, "Acme");
});

test("returns no metadata for malformed EXIF segments", () => {
  assert.equal(readExif(Buffer.from([0xff, 0xd8, 0xff, 0xe1, 0xff, 0xff])), null);
});
