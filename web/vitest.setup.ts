// Adds the jest-dom matchers (toBeInTheDocument, toHaveTextContent, ...) to Vitest's expect.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom does no layout, so it doesn't implement scrollIntoView. Anything that follows a
// growing list down the page calls it (the tutor does, on every new message), and without a
// stub the effect throws a TypeError that surfaces as some unrelated assertion failing.
Element.prototype.scrollIntoView = vi.fn();

// Unmount whatever a test rendered before the next one runs. Testing Library does this by
// itself only when Vitest's `globals` are on, and they aren't here, so without this every
// render piles up in the same document for the whole file. Tests that query unique text
// still pass, which is what makes it easy to miss: it only bites once two tests in a file
// render the same component, and then it fails as "found multiple elements" rather than
// anything that points at the real cause.
afterEach(cleanup);
