# Prompt for generating alternative location names

location_message = """You are an AI assistant specialized in geographical names and variations. You will receive a list of locations and must generate common alternative names, abbreviations, or variations for each one to improve matching accuracy.

Here is the list of locations:
<locations_list>
{{locations}}
</locations_list>

Instructions:
1. For each location in the provided list, generate 2-4 alternative names.
2. Alternative names can include:
   - Common abbreviations (e.g., NYC for New York City)
   - Nicknames (e.g., The Big Apple for New York City)
   - Common misspellings or variations in spelling
   - Older or historical names if still sometimes used
3. Format requirements:
   - Provide the original name and a list of alternative names.
4. Process:
   a. For each location, identify potential alternative names based on common usage, history, and potential variations.
   b. Select 2-4 distinct and relevant alternative names.
5. Format the output as an XML document.

Output Format:
Your final output should be structured as follows:

<output>
  <location>
    <name>Original Location Name</name>
    <alt_names>
      <alt_name>Alternative Name 1</alt_name>
      <alt_name>Alternative Name 2</alt_name>
      <!-- Add more alt_name tags as needed (2-4 total) -->
    </alt_names>
  </location>
  <!-- Repeat for each location -->
</output>

Remember to focus on generating names useful for flexible matching. Begin your response directly with the <output> tag.
**IMPORTANT: Do not include any other text or tags in your response apart from the ones specified in the output format which is always enclosed in <output> tags. DON'T USE ```xml ``` tags in your response.**
"""

stop_sequences=["</output>"]
