import '@testing-library/jest-dom';

// jsdom doesn't implement scrollIntoView; components (e.g. the conflict queue's
// keyboard auto-scroll) call it in effects, so stub it to a no-op under test.
if (typeof window !== 'undefined') {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
}
