import { mkdir, writeFile } from 'node:fs/promises';
await mkdir('../.tools', { recursive: true });
const response = await fetch('https://registry.npmjs.org/npm/-/npm-12.2.1.tgz');
if (!response.ok) throw new Error(`npm download: ${response.status}`);
await writeFile('../.tools/npm.tgz', Buffer.from(await response.arrayBuffer()));
console.log('Downloaded official npm package to code/.tools/npm.tgz');
