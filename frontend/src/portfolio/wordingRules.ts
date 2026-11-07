// The advice words the Equity portfolio page must never show (the site's rule plus the handover pack's BANNED_WORDS, less "add", which is the button's name).
export const PAGE_BANNED = /\b(buy|buying|sell|selling|hold|reduce|trim|exit|avoid|should|must|recommend\w*|overweight|underweight|target|accumulate|switch|book profits?|best|multibagger|top pick)\b/i;
export const FAQ_BANNED = PAGE_BANNED;
