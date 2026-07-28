import '@testing-library/jest-dom';
import { deserialize, serialize } from 'node:v8';

// jsdom builds its own global object and does not carry `structuredClone`, even
// though every browser we target and Node itself both have it. Without this,
// any module that deep-clones on the way out of a mock API — `lib/packs.ts`,
// `lib/documents.ts`, `lib/decisions.ts` — throws ReferenceError under test
// while working perfectly in the app.
//
// v8.serialize round-trips rather than JSON: JSON would quietly turn a Date into
// a string and drop `undefined`, so a test could pass against a shape the app
// never actually produces.
if (typeof globalThis.structuredClone !== 'function') {
  globalThis.structuredClone = <T>(value: T): T => deserialize(serialize(value)) as T;
}
