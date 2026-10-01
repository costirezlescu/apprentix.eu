/* Lets `node --test worker/test` (a directory) run every test file: Node resolves the
   directory to this file. `npm test` runs the files directly. */
import './bm25.test.js';
import './tools.test.js';
import './http.test.js';
import './loop.test.js';
