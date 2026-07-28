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

// jsdom parses <dialog> but does not implement its methods, so `showModal()` is
// undefined and `components/ui/dialog.tsx` throws the moment a modal opens. That
// component is built on the native element deliberately — the platform gives it
// focus trapping, Escape-to-close and an inert background for free — so the gap
// is in the test environment, not in the code.
//
// This models the observable contract the component relies on: `open` reflects
// state, and `close()` fires a `close` event (the component wires `onClose` to
// it). The top layer, the ::backdrop and real focus trapping are not modelled —
// jsdom has no concept of them, so assertions must not depend on them.
const dialogProto = globalThis.HTMLDialogElement?.prototype;
if (dialogProto && typeof dialogProto.showModal !== 'function') {
  dialogProto.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  dialogProto.show = function show(this: HTMLDialogElement) {
    this.open = true;
  };
  dialogProto.close = function close(this: HTMLDialogElement, returnValue?: string) {
    this.open = false;
    if (returnValue !== undefined) this.returnValue = returnValue;
    this.dispatchEvent(new Event('close'));
  };
}
