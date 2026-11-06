// Hand-written set for /holdings (the new My portfolio page): the six questions of the design. It takes the place of the PDF-built set for this route
// (lib/pageFaqs.ts lists hand-written sets first). Descriptive only; information, not investment advice.
import type { PageFaq } from "./pageFaqs";

export const MY_PORTFOLIO_FAQ: PageFaq = {
  id: "my-portfolio", title: "My portfolio", section: "Your workspace", routes: ["/holdings"],
  items: [
    { q: "Why does FinLit not ask for quantities?", a: "The page describes how your shares are made up and how they have moved together, which needs only the names. Not asking for amounts keeps your holdings private, and nothing here depends on them. Where an amount would change a figure, the page shows two neutral cases: equal amounts and amounts sized by company value." },
    { q: "What do \"equal amounts\" and \"company value\" mean?", a: "Equal amounts counts every share the same, as if the same rupee amount sat in each. Sized by company value counts each share in proportion to the company's market value, so bigger companies weigh more. They are two ways to read the same names; neither is your actual split." },
    { q: "How is the diversification score worked out?", a: "Score = 60% co-movement + 40% sector spread. Co-movement is how many independent shares the list moves like, from the last 104 weekly returns: 15 or more independent shares score 100 on this part. Sector spread is the number of effective sectors, counting each share once: 8 or more score 100. Both parts use a logarithmic scale. The score describes how spread out the list is, not how safe it is." },
    { q: "What is a correlation?", a: "A number from −1 to 1 for how two shares' weekly price changes line up. Near 0 means they move on their own; near 1 means they rise and fall together. Pairs of 0.5 or more move together clearly; 0.65 or more move almost as one." },
    { q: "What do the colours mean?", a: "Scores run 0 to 100: green from 70, orange 50 to 69, red under 50. This goes for the overall score and for each part. For the Risk part, a high score means lower risk. Colours describe the score only." },
    { q: "How many shares can I add?", a: "The number on your plan is shown beside the add bar. Names beyond it are left out and listed, never guessed." },
  ],
};
