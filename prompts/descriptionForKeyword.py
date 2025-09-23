keyword_message="""You are a technical writer specializing in standardized skill descriptions for vector-based matching systems. Generate descriptions for the following keywords:

<keywords>
{{INSERT_KEYWORDS}}
</keywords>

For each keyword, create a 300-word standardized description that includes:
1. Core definition and fundamental aspects of the skill
2. Standard industry applications and use cases
3. Common tools, methodologies, and best practices
4. Related skills and knowledge areas
5. Key responsibilities typically associated with the skill
6. Industry-standard processes and workflows
7. Common challenges and considerations

Guidelines:
- Use standardized industry terminology
- Focus on widely-accepted practices rather than specific achievements
- Avoid numerical metrics or specific project details
- Include standard tools and methodologies
- Maintain consistent structure across all descriptions
- Use general terms that support vector matching
- Focus on universal applications rather than specific scenarios

Output format:
<output>
  <keywords>
    <keyword>
      <name>[keyword name]</name>
      <description>[standardized 300-word description]</description>
    </keyword>
  </keywords>
</output>

**IMPORTANT: Do not include any other text or tags in your response apart from the ones specified in the output format which is always inclosed in <output> tags. DON'T USE ```xml ``` tags in your response.**
"""
stop_sequences = ["</output>"]