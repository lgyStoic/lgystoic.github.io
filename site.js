async function loadNotes() {
  const source = document.body.dataset.notesSource || "./notes/notes.json";
  const response = await fetch(source);
  if (!response.ok) throw new Error(`Unable to load ${source}`);
  return response.json();
}

function getNoteUrl(note) {
  const base = document.body.dataset.notesBase || ".";
  if (base === "root") return note.url;
  return note.absoluteUrl || note.url;
}

function renderNoteCard(note) {
  const tags = [note.source, ...(note.tags || [])]
    .filter(Boolean)
    .map((tag) => `<span>${tag}</span>`)
    .join("");

  return `
    <article class="note-card">
      <div class="note-meta">${tags}</div>
      <h3>${note.title}</h3>
      <p>${note.summary}</p>
      <div class="note-actions">
        <a class="button" href="${getNoteUrl(note)}">打开笔记</a>
        <span>${note.status || "草稿"} · ${note.updated || ""}</span>
      </div>
    </article>
  `;
}

async function hydrateNotes() {
  const targets = [...document.querySelectorAll("[data-notes-list]")];
  if (!targets.length) return;

  try {
    const notes = await loadNotes();
    targets.forEach((target) => {
      const mode = target.dataset.notesList;
      const visibleNotes = mode === "featured" ? notes.filter((note) => note.featured) : notes;
      target.innerHTML = visibleNotes.map(renderNoteCard).join("");
    });
  } catch (error) {
    console.warn(error);
  }
}

hydrateNotes();
