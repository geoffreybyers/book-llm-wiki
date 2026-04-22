# Lens Library

Lenses are free-text fragments prepended to the synthesis prompt. They
shape what the Critical Pass focuses on for different kinds of books.

## general

Standard non-fiction analytical lens. Extract the central thesis, the top
5–10 novel claims, and apply the Critical Pass. Prefer claims that are
falsifiable; flag those that aren't.

## self_help

Self-help and productivity books. The central risk is confident prose
wrapping thin evidence. For every claim, ask: is this supported by cited
studies, or by anecdote and authority? Weak claims and facts-to-verify are
the most important sections here.

## business

Business and strategy books. Claims often rest on survivorship bias
("study 10 successful companies, extract common traits"). In the Critical
Pass, explicitly flag reasoning that could apply equally to failed companies.

## philosophy

Philosophy and ideas books. Steelman each argument charitably. Weak-claims
is less about empirical support and more about internal consistency — does
the conclusion follow from the premises?

## memoir

Memoir and biography. Weak-claims and facts-to-verify largely N/A. Focus on
TL;DR, Key Insights (what the subject learned, not claims about the world),
and Chapter by Chapter. Critical Pass reduced to steelman only.

## fiction

Fiction. Critical Pass is N/A — no empirical claims to verify. Focus on
plot, themes, Key Insights (character arcs, thematic claims the author
makes implicitly), and Chapter by Chapter.

## Writing new lenses

Edit `books.yaml` → `lenses:` to add one. A good lens names:
1. The dominant frame for insights (e.g. "mechanism-level causal claims").
2. What's signal vs noise (e.g. "author's self-deprecating asides are signal").
3. Per-genre extraction rules (e.g. "every claim about 'the research' must be
   verified — most self-help citations are either misrepresented or fake").
