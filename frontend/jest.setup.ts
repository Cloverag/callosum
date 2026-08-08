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

// The <dialog> polyfill that stood here was removed with the native-element
// dialog it existed for (2026-08-09). `components/ui/dialog.tsx` is now built on
// Base UI, which renders an ordinary div through a portal, so jsdom's missing
// `showModal()` no longer sits on any code path.
//
// jsdom does not implement ResizeObserver, and every Base UI component that
// positions a floating element against an anchor — Select, Popover, Tooltip,
// DropdownMenu — observes its anchor with one. Without this they throw on the
// first open. The calendar's meeting form is the live case: its status Select
// renders inside the detail dialog that `CalendarPage.test.tsx` opens.
//
// A no-op is the honest model here: jsdom has no layout engine, so every box it
// could report would be 0×0 anyway. Assertions must not depend on measured size
// or on which side a popup was placed.
if (typeof globalThis.ResizeObserver !== 'function') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
