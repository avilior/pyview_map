// ---------------------------------------------------------------------------
// DynamicList — highlight hook for scrollable list component
// ---------------------------------------------------------------------------

window.Hooks = window.Hooks ?? {};

window.Hooks.DynamicList = {
  mounted() {
    const cid = this.el.id;
    this.handleEvent(`${cid}:highlightListItem`, ({id}) => {
      // Stream items get dom IDs like "{component_id}-list-items-{id}"
      const item = document.getElementById(`${cid}-list-items-${id}`);
      if (!item) return;
      item.scrollIntoView({behavior: 'smooth', block: 'nearest'});
      item.classList.add('list-item-highlight');
      setTimeout(() => item.classList.remove('list-item-highlight'), 2000);
    });
  },
};
