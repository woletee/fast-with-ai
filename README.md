# Fast, With AI

A companion to Patrick Collison's [Fast](https://patrickcollison.com/fast): big things done fast with AI, how long each took, and what the AI did.

Static site: `index.html` plus card images in `img/`. Card images are each project's own preview image and belong to their owners.

## Adding an entry

1. Anyone opens **[Suggest an entry](https://github.com/woletee/fast-with-ai/issues/new?template=new-entry.yml)** and fills in the short form (about 3 minutes).
2. A bot checks the form and the source link, then comments on the issue.
3. A maintainer checks the claims against the source and adds the `approved` label.
4. The bot adds the entry to `data/entries.json`, saves the source's preview image as the card image, credits the source, and closes the issue. The site updates in a minute or two.

Entries live in `data/entries.json`; the page loads them at runtime.
