#!/usr/bin/env node
/**
 * Bump the patch version in package.json.
 * Usage: node scripts/bump-version.js [major|minor|patch]
 * Defaults to "patch" if no argument is given.
 */
const fs = require("fs");
const path = require("path");

const pkgPath = path.resolve(__dirname, "..", "package.json");
const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));

const [major, minor, patch] = pkg.version.split(".").map(Number);
const part = process.argv[2] || "patch";

let newVersion;
switch (part) {
  case "major":
    newVersion = `${major + 1}.0.0`;
    break;
  case "minor":
    newVersion = `${major}.${minor + 1}.0`;
    break;
  case "patch":
  default:
    newVersion = `${major}.${minor}.${patch + 1}`;
    break;
}

pkg.version = newVersion;
fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n", "utf8");
console.log(`${pkg.version}`);
