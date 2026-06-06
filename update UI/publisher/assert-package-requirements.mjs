import { readFileSync } from 'node:fs';

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

if (!process.env.PUBLISH_PACKAGE_REQUIREMENTS) {
  fail('PUBLISH_PACKAGE_REQUIREMENTS is required');
}

const publisherPackageJson = readJson(
  new URL('./package.json', import.meta.url)
);
const requirements = JSON.parse(process.env.PUBLISH_PACKAGE_REQUIREMENTS);
const errors = [];

for (const sectionName of ['dependencies', 'devDependencies']) {
  const expectedSection = requirements[sectionName] ?? {};
  const actualSection = publisherPackageJson[sectionName] ?? {};

  for (const [packageName, expectedVersion] of Object.entries(
    expectedSection
  )) {
    const actualVersion = actualSection[packageName];
    if (actualVersion !== expectedVersion) {
      errors.push(
        `${sectionName}.${packageName}: expected ${expectedVersion}, found ${actualVersion ?? 'missing'}`
      );
    }
  }
}

if (errors.length > 0) {
  fail(`Publisher package requirements drifted:\n${errors.join('\n')}`);
}
