import MarkdownIt from "markdown-it";

const MAX_FORMATTED_CHARACTERS = 64 * 1024;
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });

export const renderMarkdown = (value: string): string => {
  const bounded = value.length > MAX_FORMATTED_CHARACTERS
    ? `${value.slice(0, MAX_FORMATTED_CHARACTERS)}\n\nOutput shortened.`
    : value;
  return markdown.render(bounded);
};
