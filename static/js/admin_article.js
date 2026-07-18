(function () {
  const container = document.getElementById("blocks-container");
  const orderInput = document.getElementById("blocks-order");
  const form = document.getElementById("article-form");
  let counter = 0;

  function updateBlocksOrder() {
    const ids = Array.from(container.children).map((row) => row.dataset.blockId);
    orderInput.value = ids.join(",");
  }

  function wireRow(row) {
    row.querySelector('[data-action="remove"]').addEventListener("click", () => {
      row.remove();
      updateBlocksOrder();
    });
    row.querySelector('[data-action="move-up"]').addEventListener("click", () => {
      const prev = row.previousElementSibling;
      if (prev) container.insertBefore(row, prev);
      updateBlocksOrder();
    });
    row.querySelector('[data-action="move-down"]').addEventListener("click", () => {
      const next = row.nextElementSibling;
      if (next) container.insertBefore(next, row);
      updateBlocksOrder();
    });
  }

  function addBlock(type) {
    const templateId = type === "text" ? "block-template-text" : "block-template-image";
    const template = document.getElementById(templateId);
    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector(".block-row");
    const blockId = `new-${counter++}`;
    row.dataset.blockId = blockId;

    if (type === "text") {
      row.querySelector('[name="__TYPE__"]').name = `block_type_${blockId}`;
      row.querySelector('[name="__CONTENT__"]').name = `block_content_${blockId}`;
    } else {
      row.querySelector('[name="__TYPE__"]').name = `block_type_${blockId}`;
      row.querySelector('[name="__IMAGE__"]').name = `block_image_${blockId}`;
      row.querySelector('[name="__CAPTION__"]').name = `block_caption_${blockId}`;
    }

    container.appendChild(fragment);
    wireRow(container.lastElementChild);
    updateBlocksOrder();
  }

  document.getElementById("add-text-block").addEventListener("click", () => addBlock("text"));
  document.getElementById("add-image-block").addEventListener("click", () => addBlock("image"));

  Array.from(container.children).forEach(wireRow);
  updateBlocksOrder();

  form.addEventListener("submit", updateBlocksOrder);
})();
