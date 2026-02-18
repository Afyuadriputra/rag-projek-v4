import "@testing-library/jest-dom";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, "ResizeObserver", {
  writable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(window, "visualViewport", {
  writable: true,
  value: {
    width: 1024,
    height: 768,
    addEventListener: () => {},
    removeEventListener: () => {},
  },
});

Object.defineProperty(window.HTMLElement.prototype, "scrollTo", {
  writable: true,
  value: () => {},
});

Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
  writable: true,
  value: () => {},
});

class DataTransferMock {
  private _files: File[] = [];
  items = {
    add: (file: File) => {
      this._files.push(file);
    },
    clear: () => {
      this._files = [];
    },
  };

  get files() {
    const files = this._files as unknown as FileList;
    return files;
  }
}

Object.defineProperty(window, "DataTransfer", {
  writable: true,
  value: DataTransferMock,
});
