/* Configure only the isolated page; all intent ownership remains shared. */
import "/receipt-static/app.js";
import { readUsageBody, decodeUsage, clearAccounting, renderAccounting } from "./accounting.js";

globalThis.startSavedSourceReceiptPage({
  storageName: "saved-source-usage:v1",
  postPath: run => `/api/runs/${run}/saved-source-usage`,
  getPath: "/api/saved-source-usage-receipts",
  readResponse: readUsageBody,
  decode: decodeUsage, clearExtra: clearAccounting, renderExtra: renderAccounting,
});
