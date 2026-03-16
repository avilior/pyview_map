// ---------------------------------------------------------------------------
// DynamicList — highlight hook for scrollable list component
// ---------------------------------------------------------------------------

window.Hooks = window.Hooks ?? {};

window.Hooks.DynamicList = {
  mounted() {
    const channel = this.el.id;
    this.handleEvent(`${channel}:highlightListItem`, ({id}) => {
      // Stream items get dom IDs like "{channel}-list-items-{id}"
      const item = document.getElementById(`${channel}-list-items-${id}`);
      if (!item) return;
      item.scrollIntoView({behavior: 'smooth', block: 'nearest'});
      item.classList.add('list-item-highlight');
      setTimeout(() => item.classList.remove('list-item-highlight'), 2000);
    });
    this.pushEvent("list-ready", {});
  },
};
