/* Localize the composer's starter topics.
 *
 * The English topics stay in index.html as the default. A Chinese reader
 * otherwise got English buttons, and with "auto" report language an English
 * topic yields an English report. Chinese topics are fine downstream: the
 * pipeline plans its English search phrase from any topic language.
 *
 * Kept out of i18n.js (hash-locked by a frozen experiment, see
 * samples_i18n.js) and out of app.js (its browser contracts strip imports).
 * app.js reads data-topic at click time, so rewriting it here is enough.
 * Loaded after app.js, so app.js has already switched the language by the
 * time this change listener runs. */

import { language } from "./i18n.js";

// [button text, submitted topic], in the markup's button order.
const TOPICS = {
  "Simplified Chinese": [
    ["电动汽车用固态电池", "电动汽车用固态电池"],
    ["CRISPR 基因编辑治疗遗传病", "CRISPR 基因编辑治疗遗传病"],
    ["工业碳捕集与封存", "工业排放源的碳捕集与封存"],
  ],
};

const buttons = [...document.querySelectorAll("#starters .starter")];
const english = buttons.map((button) => [button.textContent.trim(), button.dataset.topic]);

function applyStarters() {
  const table = TOPICS[language()] ?? english;
  buttons.forEach((button, index) => {
    const [text, topic] = table[index] ?? english[index];
    button.textContent = text;
    button.dataset.topic = topic;
  });
}

applyStarters();
document.querySelector("#ui-lang")?.addEventListener("change", () => applyStarters());
