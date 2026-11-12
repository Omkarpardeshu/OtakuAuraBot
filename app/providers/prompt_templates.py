DETAIL_GUIDANCE = {
    "quick": "Be concise. Include only the most important visible details.",
    "standard": "Create a balanced prompt with the main subject, setting, composition, lighting, colours, and style.",
    "detailed": "Be highly descriptive. Include visible subject details, pose/action, clothing when clearly visible, environment, composition, camera viewpoint, lighting, colour palette, textures, and visual style.",
    "maximum": "Be exceptionally thorough while staying faithful to the image. Cover meaningful visible details, spatial relationships, framing, perspective, lighting, palette, materials, textures, atmosphere, and style. Avoid redundancy.",
}

MODE_GUIDANCE = {
    "natural": "Write one fluent, coherent natural-language image-generation prompt as a paragraph. Do not use headings or a tag list.",
    "tags": "Act as a specialist anime-illustration tagger for image-generation prompts. Return ONLY one comma-separated line of concise Danbooru/NovelAI-inspired tags; never return prose, headings, bullets, numbering, Markdown, explanations, or a sentence. Order tags consistently: (1) visible subject count/type such as 1girl, 1boy, 2girls, solo when clearly supported; (2) hair style/colour, eyes, expression and gaze; (3) pose, action and framing; (4) clothing and visible accessories; (5) held objects and nearby objects; (6) setting, background, weather/time; (7) lighting, palette, viewpoint and supported anime art-style tags. Prefer established, specific tags over descriptive phrases. Include only details that can be seen in the image. Do not infer exact character identity, age, personality, relationship, hidden anatomy, story, location, or text. Do not add anatomy or sexualized tags unless clearly visible, relevant and appropriate; never sexualize a young-looking or age-ambiguous character. Do not add generic quality tags (masterpiece, best quality, etc.) unless the user explicitly requests them. Remove synonyms, duplicates, contradictions, vague filler and unsupported tags. Preserve distinctive visible details without over-tagging. Output a single line.",
    "enhanced": "Write a polished, richly descriptive image-generation prompt. Organize it into compact labeled sections: Subject and action; Environment and composition; Lighting and colour; Style and details. Keep every detail grounded in the image.",
}

LANGUAGES = {"English": "English", "Hindi": "Hindi", "Hinglish": "Hinglish"}
