#!/usr/bin/env node
/**
 * Bump version and/or commit + tag + push.
 *
 * Usage:
 *   node scripts/bump-version.js patch           # bump patch, print new version
 *   node scripts/bump-version.js minor           # bump minor
 *   node scripts/bump-version.js major           # bump major
 *   node scripts/bump-version.js --tag           # commit, tag, push current version (no bump)
 *   node scripts/bump-version.js patch --tag     # bump patch, then commit + tag + push
 */
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const pkgPath = path.resolve(__dirname, "..", "package.json");
const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));

const args = process.argv.slice(2);
const doTag = args.includes("--tag");
const part = args.find((a) => ["major", "minor", "patch"].includes(a));

if (part) {
  const [major, minor, patch] = pkg.version.split(".").map(Number);
  switch (part) {
    case "major":
      pkg.version = `${major + 1}.0.0`;
      break;
    case "minor":
      pkg.version = `${major}.${minor + 1}.0`;
      break;
    case "patch":
      pkg.version = `${major}.${minor}.${patch + 1}`;
      break;
  }
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n", "utf8");
}

console.log(pkg.version);

if (doTag) {
  const run = (cmd) => {
    console.log(`> ${cmd}`);
    execSync(cmd, { stdio: "inherit", cwd: path.resolve(__dirname, "..") });
  };
  run("git add -A");
  run(`git commit -m "v${pkg.version}"`);
  run(`git tag v${pkg.version}`);
  run(`git push origin main v${pkg.version}`);
}
