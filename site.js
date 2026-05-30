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

function renderEmptyCard() {
  return `
    <article class="note-card ghost">
      <div class="note-meta">
        <span>Next</span>
        <span>Template</span>
      </div>
      <h3>下一份资料可以从模板开始</h3>
      <p>复制 <code>templates/note/</code> 到 <code>notes/your-slug/</code>，再把新条目写进 <code>notes/notes.json</code>。</p>
      <a class="button secondary" href="https://github.com/lgyStoic/lgystoic.github.io/tree/master/templates/note" rel="noreferrer">查看模板</a>
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
      target.innerHTML = visibleNotes.map(renderNoteCard).join("") + (mode === "featured" ? renderEmptyCard() : "");
    });
  } catch (error) {
    console.warn(error);
  }
}

hydrateNotes();
