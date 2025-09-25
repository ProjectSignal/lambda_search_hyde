# logicalHyde.py

import sys
import os
import json
import asyncio
import re
from typing import Dict, Any, List
import xml.etree.ElementTree as ET  # for parsing XML output
from datetime import datetime as dt
# from logging_config import setup_logger
# logger = setup_logger(__name__)

import logging
logger = logging.getLogger(__name__)
from prompts.logicalHyde import exampleKeyword, messageKeyword
from prompts.descriptionForLocationNew import location_message as location_message_new, stop_sequences as location_stop_sequences_new
from prompts.descriptionForKeyword import keyword_message, stop_sequences as keyword_stop_sequences
from db import r
from llm_helper import LLMManager
from utils import normalize_text


###############################################################################
# HELPER: PARSE LOCATION XML (New format)
###############################################################################
def parse_location_xml(xml_string: str) -> List[Dict[str, Any]]:
    """
    Given an XML string in the format:

    <output>
      <location>
        <name>...</name>
        <alt_names>
          <alt_name>...</alt_name>
          <alt_name>...</alt_name>
        </alt_names>
      </location>
      <!-- Repeat for each location -->
    </output>

    Returns: [ { "name": ..., "alt_names": [...] }, ... ]
    """
    results = []
    try:
        # Simple check to remove markdown code block identifiers
        if xml_string.startswith("```xml"):
            xml_string = xml_string.replace("```xml", "", 1)
            logger.info("Removed markdown XML identifier from response")
        elif xml_string.startswith("```"):
            xml_string = xml_string.replace("```", "", 1)
            logger.info("Removed generic markdown identifier from response")

        if xml_string.endswith("```"):
            xml_string = xml_string[:-3]
            logger.info("Removed closing markdown identifier from response")

        xml_string = xml_string.strip()

        output_start = xml_string.find("<output>")
        if output_start == -1:
            logger.error("No <output> tag found in XML response")
            return results

        output_end = xml_string.find("</output>", output_start)
        if output_end == -1:
            logger.error("No closing </output> tag found in XML response")
            return results

        output_xml = xml_string[output_start:output_end + len("</output>")]
        root = ET.fromstring(output_xml)

        for loc_elem in root.findall("location"):
            name_elem = loc_elem.find("name")
            alt_names_elem = loc_elem.find("alt_names")
            loc_name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            alt_names_list = []
            if alt_names_elem is not None:
                for alt_name_elem in alt_names_elem.findall("alt_name"):
                    if alt_name_elem.text:
                        alt_names_list.append(alt_name_elem.text.strip())

            if loc_name:  # Only add if we have a name
                results.append({"name": loc_name, "alt_names": alt_names_list})
        logger.info(
            f"Successfully parsed {len(results)} locations with alt names from XML: {[r['name'] for r in results]}")
    except ET.ParseError as e:
        logger.error(f"Failed to parse location XML: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error parsing location XML: {str(e)}")
    return results


###############################################################################
# ASYNC FUNCTION: GET LOCATION ALTERNATIVE NAMES
#   + XML parsing from the LLM output
###############################################################################
async def get_chat_completion_location_alt_names(locations: List[str], provider: str = "deepseek") -> List[Dict[str, Any]]:
    """
    Generate location alternative names using the LLM. We parse the final XML output.
    Returns list of dicts: [{ "name": ..., "alt_names": [...] }, ...]
    """
    logger.info(
        f"Generating location alternative names for batch: {locations}")
    llm = LLMManager()

    # Format locations for the new prompt
    locations_str = "\n".join(locations)
    user_prompt = location_message_new.replace("{{locations}}", locations_str)

    messages = [{"role": "user", "content": user_prompt}]
    try:
        response = await llm.get_completion(
            provider=provider,
            messages=messages,
            fallback=True,  # Use fallback if primary fails
            stop=location_stop_sequences_new,  # Use new stop sequences
        )
        response_text = response.choices[0].message.content + \
            location_stop_sequences_new[0]
        parsed_list = parse_location_xml(
            response_text)  # Use the updated parser
        if not parsed_list:
            logger.warning(
                "Failed to parse XML response for locations, returning empty list")
            # Return list with original names and empty alt_names lists for robustness
            return [{"name": loc, "alt_names": []} for loc in locations]

        # Create a map for easier lookup
        parsed_map = {item['name']: item['alt_names'] for item in parsed_list}

        # Ensure all original locations are present in the result, even if parsing failed for some
        final_results = []
        for loc in locations:
            if loc in parsed_map:
                final_results.append(
                    {"name": loc, "alt_names": parsed_map[loc]})
            else:
                logger.warning(
                    f"Location '{loc}' not found in parsed LLM response. Returning with empty alt_names.")
                final_results.append({"name": loc, "alt_names": []})
        return final_results

    except Exception as e:
        logger.error(
            f"Error during LLM call or parsing for location alt names: {e}")
        # Return list with original names and empty alt_names lists on error
        return [{"name": loc, "alt_names": []} for loc in locations]


###############################################################################
# CACHING HELPERS:
#   - Fetch/Generate Alternative Names for Locations (No Embeddings)
#   - Fetch/Generate Descriptions for Skills (No Embeddings generated here, but passed if cached)
###############################################################################

# Renamed function and updated logic for alternative names
async def process_location_alt_names(locations: List[str], provider: str = "deepseek") -> List[Dict[str, Any]]:
    """
    Check Redis for each location's alternative names. If not found, generate using LLM.
    Returns a list of dictionaries: [{ "name": "...", "alt_names": [...] }, ...]
    in the same order as the input list.
    """
    if not locations:
        return []

    logger.info(f"Processing locations for alternative names: {locations}")
    results = [None] * len(locations)
    locations_to_generate = []
    indices_to_generate = []

    # Check cache first
    for i, location in enumerate(locations):
        normalized_loc = normalize_text(location)
        cache_key = f"location_alt_names:{normalized_loc}"
        cached_data = r.get(cache_key)

        if cached_data:
            try:
                alt_names = json.loads(cached_data)
                results[i] = {"name": location, "alt_names": alt_names}
                logger.debug(f"Cache hit for location alt names: {location}")
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to decode cached JSON for location alt names: {location}. Will regenerate.")
                locations_to_generate.append(location)
                indices_to_generate.append(i)
        else:
            logger.debug(f"Cache miss for location alt names: {location}")
            locations_to_generate.append(location)
            indices_to_generate.append(i)

    # Generate missing alternative names
    if locations_to_generate:
        logger.info(
            f"Generating alt names for {len(locations_to_generate)} locations: {locations_to_generate}")
        generated_results = await get_chat_completion_location_alt_names(locations_to_generate, provider)

        # Create a map from the generated results for easy lookup
        generated_map = {res["name"]: res["alt_names"]
                         for res in generated_results}

        for i, original_index in enumerate(indices_to_generate):
            original_location_name = locations_to_generate[i]
            # Find the corresponding result (match by original name)
            # Default to empty list if not found
            alt_names = generated_map.get(original_location_name, [])
            results[original_index] = {
                "name": original_location_name, "alt_names": alt_names}

            # Cache the result
            normalized_loc = normalize_text(original_location_name)
            cache_key = f"location_alt_names:{normalized_loc}"
            try:
                r.set(cache_key, json.dumps(alt_names))
                logger.info(
                    f"Cached alt names for location: {original_location_name}")
            except Exception as e:
                logger.error(
                    f"Failed to cache alt names for {original_location_name}: {e}")

    # Ensure all results are populated (handle potential Nones if errors occurred)
    final_results = []
    for i, res in enumerate(results):
        if res is None:
            logger.error(
                f"Failed to get or generate alt names for location: {locations[i]}. Using empty list.")
            final_results.append({"name": locations[i], "alt_names": []})
        else:
            final_results.append(res)

    logger.info(
        f"Finished processing {len(locations)} locations for alt names.")
    return final_results


###############################################################################
# HELPER: PARSE KEYWORD XML
###############################################################################
def parse_keyword_xml(xml_string: str) -> Dict[str, str]:
    """
    Given an XML string in the format:

    <output>
      <keywords>
        <keyword>
          <name>some skill</name>
          <description>...</description>
        </keyword>
        ...
      </keywords>
    </output>

    Return: { "some skill": "description text", ... }
    """
    output_map = {}
    try:
        # Simple check to remove markdown code block identifiers
        if xml_string.startswith("```xml"):
            xml_string = xml_string.replace("```xml", "", 1)
            logger.info("Removed markdown XML identifier from response")
        elif xml_string.startswith("```"):
            xml_string = xml_string.replace("```", "", 1)
            logger.info("Removed generic markdown identifier from response")

        if xml_string.endswith("```"):
            xml_string = xml_string[:-3]
            logger.info("Removed closing markdown identifier from response")

        xml_string = xml_string.strip()

        # Try XML parsing first
        try:
            root = ET.fromstring(xml_string)
            keywords_elem = root.find("keywords")
            if keywords_elem is not None:
                for kw_elem in keywords_elem.findall("keyword"):
                    name_elem = kw_elem.find("name")
                    desc_elem = kw_elem.find("description")
                    kw_name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
                    kw_desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                    if kw_name:
                        output_map[kw_name] = kw_desc
                logger.info(
                    f"Successfully parsed {len(output_map)} keywords from XML: {list(output_map.keys())}")
                return output_map
        except ET.ParseError:
            logger.warning("XML parsing failed, trying regex fallback")

        # Fallback to regex parsing if XML parsing fails
        import re
        keyword_pattern = r'<keyword>\s*<name>(.*?)</name>\s*<description>(.*?)</description>\s*</keyword>'
        matches = re.findall(keyword_pattern, xml_string, re.DOTALL)

        for name, description in matches:
            name = name.strip()
            description = description.strip()
            if name:
                output_map[name] = description

        if output_map:
            logger.info(
                f"Successfully parsed {len(output_map)} keywords using regex fallback: {list(output_map.keys())}")
        else:
            logger.error("Both XML and regex parsing failed")

    except Exception as e:
        logger.error(f"Error parsing keyword XML: {str(e)}")

    return output_map


###############################################################################
# ASYNC FUNCTION: GET KEYWORD DESCRIPTIONS
#   + XML parsing from the LLM output
###############################################################################
async def get_chat_completion_description(keywords: List[str], provider: str = "deepseek") -> Dict[str, str]:
    """
    Generate a dictionary of {keyword -> description} for skill keywords using your LLM.
    We'll parse the XML output. (No embedding generation here.)
    """
    logger.info(f"Generating skill descriptions for batch: {keywords}")
    llm = LLMManager()

    keywords_xml = "\n".join(f"<keyword>{kw}</keyword>" for kw in keywords)
    user_prompt = keyword_message.replace("{{INSERT_KEYWORDS}}", keywords_xml)

    messages = [{"role": "user", "content": user_prompt}]
    response = await llm.get_completion(
        provider=provider,
        messages=messages,
        fallback=True,
        stop=keyword_stop_sequences,
    )

    response_text = response.choices[0].message.content + \
        keyword_stop_sequences[0]
    parsed_map = parse_keyword_xml(response_text)
    if not parsed_map:
        logger.warning(
            "Failed to parse XML response for keywords, returning empty map")
        return {}

    return parsed_map





###############################################################################
# CACHING HELPERS:
#   - We do NOT generate embeddings here.
#   - If Redis has stored "embeddings", we include them in the data structure.
###############################################################################
async def process_canhelp_skills_with_descriptions(skills: List[str], provider: str = "deepseek") -> Dict[str, Any]:
    """
    Processes skill names and generates descriptions (via LLM) if absent from Redis.
    If Redis has "embeddings" stored (by some other pipeline), we include them; otherwise we omit them.

    Returns: 
      { skill -> {"description": "...", "embeddings": [...]} or {"description":"..."} }
    """
    logger.info(f"Processing {len(skills)} skills for descriptions")
    all_descriptions = {}
    uncached_skills = []

    norm_skills = [normalize_text(skill) for skill in skills]
    redis_keys = [f"skill:{norm}" for norm in norm_skills]
    cached_values = r.mget(*redis_keys)

    cache_hits = []
    for skill, cached_value in zip(skills, cached_values):
        if cached_value:
            try:
                # We expect JSON: possibly containing "description" and "embeddings"
                # Handle both bytes and string return types from Redis
                if isinstance(cached_value, bytes):
                    cached_data = json.loads(cached_value.decode("utf-8"))
                else:
                    cached_data = json.loads(cached_value)
                all_descriptions[skill] = cached_data
                cache_hits.append(skill)
                logger.info(
                    f"Cache HIT for skill: {skill} - Using cached description")
            except Exception as e:
                logger.error(f"Failed parsing cached skill for {skill}: {e}")
                uncached_skills.append(skill)
                logger.info(
                    f"Cache ERROR for skill: {skill} - Will generate new description")
        else:
            uncached_skills.append(skill)
            logger.info(
                f"Cache MISS for skill: {skill} - Will generate new description")

    if cache_hits:
        logger.info(
            f"Skill cache HITS ({len(cache_hits)}/{len(skills)}): {cache_hits}")
    if uncached_skills:
        logger.info(
            f"Skill cache MISSES ({len(uncached_skills)}/{len(skills)}): {uncached_skills}")

    # Generate descriptions from LLM for uncached
    batch_size = 3
    max_concurrent_batches = 5
    semaphore = asyncio.Semaphore(max_concurrent_batches)

    async def process_batch(batch: List[str]) -> Dict[str, Any]:
        async with semaphore:
            try:
                logger.info(f"Generating descriptions for batch: {batch}")
                batch_descriptions = await get_chat_completion_description(batch, provider)
                logger.info(
                    f"Successfully generated descriptions for batch: {list(batch_descriptions.keys())}")

                # Store in Redis only "description" if not present
                for skill_name, skill_desc in batch_descriptions.items():
                    skill_obj = {
                        "description": skill_desc
                        # No "embeddings" here
                    }
                    all_descriptions[skill_name] = skill_obj

                    # Log successful generation and caching
                    logger.info(
                        f"Generated and cached new description for skill: {skill_name}")
                return batch_descriptions
            except Exception as e:
                logger.error(f"Error processing skill batch: {str(e)}")
                return {}

    batches = [uncached_skills[i:i + batch_size]
               for i in range(0, len(uncached_skills), batch_size)]
    await asyncio.gather(*[process_batch(batch) for batch in batches])

    return all_descriptions


# REMOVED: not used anymore, moved to altNames instead
# async def process_location_descriptions(locations: List[str], provider: str = "deepseek") -> List[Dict[str, Any]]:
    # """
    # Check Redis for each location. If found, return that object (which might include "embeddings").
    # If not found, we generate only the 'description' from LLM, store in Redis (no embeddings).
    # Return a list in the same order, possibly including "embeddings" if found in cache.
    # """
    # logger.info(f"Processing {len(locations)} locations for descriptions")
    final_descriptions: List[Dict[str, Any]] = [None] * len(locations)
    uncached_indices = []
    uncached_locs = []

    norm_to_orig = {normalize_text(loc): loc for loc in locations}
    norm_locations = list(norm_to_orig.keys())
    redis_keys = [f"location:{norm}" for norm in norm_locations]
    cached_values = r.mget(*redis_keys)

    cache_hits = []
    for idx, (norm_loc, cached_value) in enumerate(zip(norm_locations, cached_values)):
        orig_loc = norm_to_orig[norm_loc]
        if cached_value:
            try:
                # Handle both bytes and string return types from Redis
                if isinstance(cached_value, bytes):
                    cached_data = json.loads(cached_value.decode("utf-8"))
                else:
                    cached_data = json.loads(cached_value)
                cached_data["name"] = orig_loc
                final_descriptions[idx] = cached_data
                cache_hits.append(orig_loc)
                logger.info(
                    f"Cache HIT for location: {orig_loc} - Using cached description")
            except Exception as e:
                logger.error(
                    f"Failed parsing cached location for {orig_loc}: {e}")
                uncached_indices.append(idx)
                uncached_locs.append(orig_loc)
                logger.info(
                    f"Cache ERROR for location: {orig_loc} - Will generate new description")
        else:
            uncached_indices.append(idx)
            uncached_locs.append(orig_loc)
            logger.info(
                f"Cache MISS for location: {orig_loc} - Will generate new description")

    if cache_hits:
        logger.info(
            f"Location cache HITS ({len(cache_hits)}/{len(locations)}): {cache_hits}")
    if uncached_locs:
        logger.info(
            f"Location cache MISSES ({len(uncached_locs)}/{len(locations)}): {uncached_locs}")

    if uncached_locs:
        logger.info(
            f"Generating descriptions for uncached locations: {uncached_locs}")
        generated = await get_chat_completion_location(uncached_locs, provider)
        logger.info(
            f"Successfully generated descriptions for locations: {[loc['name'] for loc in generated]}")

        for gen_idx, loc_data in enumerate(generated):
            location_name = loc_data["name"]
            loc_obj = {
                "name": location_name,
                "description": loc_data.get("description", "")
            }
            # final_descriptions assignment
            if gen_idx < len(uncached_indices):
                final_descriptions[uncached_indices[gen_idx]] = loc_obj
                logger.info(
                    f"Generated and cached new description for location: {location_name}")

    final_output = [desc for desc in final_descriptions if desc is not None]
    return final_output


###############################################################################
# MAIN HYDE CLASS
###############################################################################
class HydeReasoning:
    """
    A new version of the HyDE reasoning with a 2-step approach:
      1) Generate structured JSON (no descriptions) using 'logicalHyde' prompts.
      2) Then fill skill + location descriptions from the cache or LLM (but NOT embeddings).
         If "embeddings" is found in the cache, pass it along; otherwise do not generate them here.
    """

    def __init__(self, hyde_provider: str = "azure-gpt-4.1-mini", description_provider: str = "gemini"):
        self.llm = LLMManager()
        self.hyde_provider = hyde_provider
        self.description_provider = description_provider
        logger.info(
            f"Initialized HydeReasoning with hyde_provider: {hyde_provider}, description_provider: {description_provider}")

    async def _call_hyde_llm(self, query: str) -> Dict[str, Any]:
        """
        STEP 1: Call the LLM with 'logicalHyde' prompts to get base JSON structure (no descriptions).
        """
        try:
            logger.info(f"Analyzing query (2-step approach), step 1: {query}")
            # Get current date and inject it into the prompt
            current_date = dt.now().strftime("%Y-%m-%d")
            prompt = messageKeyword.replace("{{query}}", query).replace(
                "{{current_date}}", current_date)
            logger.info(
                f"Using provider: {self.hyde_provider} with current date: {current_date}")
            response = await self.llm.get_completion(
                provider=self.hyde_provider,
                messages=[
                    {"role": "user", "content": exampleKeyword},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0
            )

            response_text = response.choices[0].message.content
            logger.info(f"Raw LLM response text:\n{response_text}")

            # First try to extract JSON from between ```json and ``` if present
            json_match = re.search(
                r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1).strip()
                logger.info("Extracted JSON from code block markers")
            else:
                response_text = response_text.strip()
                logger.info("Using raw response text")

            # Clean up the JSON string if needed
            if not response_text.startswith("{"):
                idx = response_text.find("{")
                if idx != -1:
                    response_text = response_text[idx:]
            if not response_text.endswith("}"):
                idx = response_text.rfind("}")
                if idx != -1:
                    response_text = response_text[:idx+1]

            try:
                parsed_json = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {str(e)}")
                # Return fallback structure
                return {
                    "query_breakdown": {
                        "key_components": [],
                        "analysis": ""
                    },
                    "response": {
                        "regionBasedQuery": 0,
                        "locationDetails": {"operator": "AND", "locations": []},
                        "organisationBasedQuery": 0,
                        "organisationDetails": {"operator": "AND", "organizations": []},
                        "sectorBasedQuery": 0,
                        "sectorDetails": {"operator": "OR", "sectors": []},
                        "skillBasedQuery": 0,
                        "skillDetails": {"operator": "AND", "skills": []},
                        "dbBasedQuery": 0,
                        "dbQueryDetails": {"operator": "AND", "queries": []}
                    }
                }

            if not isinstance(parsed_json, dict):
                raise ValueError("Invalid JSON format (not a dict).")

            if "query_breakdown" not in parsed_json or "response" not in parsed_json:
                logger.warning(
                    "No 'query_breakdown' or 'response' found in the JSON. Returning entire JSON.")
                return parsed_json

            # Normalize dbQueryDetails fields to align with our DB schema
            try:
                response_part = parsed_json.get("response", {})
                if response_part and response_part.get("dbBasedQuery"):
                    db_details = response_part.get("dbQueryDetails", {})
                    queries = db_details.get("queries", [])
                    for q in queries:
                        field_name = q.get("field")
                        if isinstance(field_name, str) and field_name.startswith("education.") and "schoolName" in field_name:
                            new_field = field_name.replace("schoolName", "school")
                            logger.info(f"Normalized DB field from '{field_name}' to '{new_field}'")
                            q["field"] = new_field
            except Exception as norm_err:
                logger.warning(f"Failed to normalize dbQueryDetails fields: {norm_err}")

            return parsed_json

        except Exception as e:
            logger.error(f"Error analyzing query: {str(e)}")
            return {
                "query_breakdown": {
                    "key_components": [],
                    "analysis": ""
                },
                "response": {
                    "regionBasedQuery": 0,
                    "locationDetails": {"operator": "AND", "locations": []},
                    "organisationBasedQuery": 0,
                    "organisationDetails": {"operator": "AND", "organizations": []},
                    "sectorBasedQuery": 0,
                    "sectorDetails": {"operator": "OR", "sectors": []},
                    "skillBasedQuery": 0,
                    "skillDetails": {"operator": "AND", "skills": []},
                    "dbBasedQuery": 0,
                    "dbQueryDetails": {"operator": "AND", "queries": []}
                }
            }

    async def _enrich_locations(self, response_data: Dict[str, Any]):
        """
        STEP 2A: If regionBasedQuery=1, fill each location with alternative names from cache or new generation.
                 If "embeddings" is in the cache, pass it along. Otherwise do not generate them here.
        """
        if response_data.get("regionBasedQuery", 0) == 1:
            loc_info = response_data.get("locationDetails", {})
            loc_list = loc_info.get("locations", [])
            if not isinstance(loc_list, list):
                return

            location_names = [loc.get("name")
                              for loc in loc_list if loc.get("name")]
            if location_names:
                enriched = await process_location_alt_names(location_names, self.description_provider)
                name_to_desc = {item["name"]: item for item in enriched}
                for loc_item in loc_list:
                    loc_name = loc_item.get("name")
                    if loc_name in name_to_desc:
                        e_obj = name_to_desc[loc_name]
                        loc_item["alt_names"] = e_obj.get("alt_names", [])

    async def _enrich_skills(self, response_data: Dict[str, Any], alternative_skills: bool):
        """
        STEP 2B: If skillBasedQuery=1, fill each skill with a description from cache or LLM (no embeddings generated).
                 If "embeddings" is in cache, we pass it along. 
                 Also handle related roles if alternative_skills=True.
                 Handle skill data processing.
        """
        if response_data.get("skillBasedQuery", 0) == 1:
            skill_info = response_data.get("skillDetails", {})
            skill_list = skill_info.get("skills", [])
            if not isinstance(skill_list, list):
                return

            skills_needing_descriptions = []
            for skill_item in skill_list:
                skill_name = skill_item.get("name", "")
                if skill_name:
                    skills_needing_descriptions.append(skill_name)

            related_role_names = []
            if alternative_skills:
                for skill_item in skill_list:
                    roles = skill_item.get("relatedRoles", [])
                    if isinstance(roles, list):
                        for r_ in roles:
                            if isinstance(r_, dict) and "name" in r_:
                                related_role_names.append(r_["name"])
                            elif isinstance(r_, str):
                                related_role_names.append(r_)
                            else:
                                related_role_names.append(str(r_))

            all_skills_to_fetch = skills_needing_descriptions + related_role_names
            skill_map = {}
            if all_skills_to_fetch:
                skill_map = await process_canhelp_skills_with_descriptions(all_skills_to_fetch, self.description_provider)

            for skill_item in skill_list:
                nm = skill_item.get("name", "")
                desc_obj = skill_map.get(nm, {})
                skill_item["description"] = desc_obj.get("description", "")
                # Pass Redis cache key instead of embeddings for efficient retrieval in Fetch
                skill_item["cache_key"] = f"skill:{normalize_text(nm)}"

                if alternative_skills:
                    roles = skill_item.get("relatedRoles", [])
                    new_related = []
                    for r_ in roles:
                        if isinstance(r_, dict):
                            r_name = r_.get("name", "")
                        elif isinstance(r_, str):
                            r_name = r_
                        else:
                            r_name = str(r_)

                        r_desc = skill_map.get(r_name, {})
                        updated_role = {
                            "name": r_name,
                            "description": r_desc.get("description", ""),
                            # Pass Redis cache key for efficient retrieval in Fetch
                            "cache_key": f"skill:{normalize_text(r_name)}"
                        }
                        new_related.append(updated_role)
                    skill_item["relatedRoles"] = new_related

    async def analyze_query(self, query: str, alternative_skills: bool = False) -> Dict[str, Any]:
        """
        Main method:
          1) Generate base JSON from LLM (no descriptions).
          2) Enrich location & skill data from the cache or LLM (no embeddings generated here).
        """
        logger.info(f"Starting query analysis for: {query}")
        base_json = await self._call_hyde_llm(query)
        if "response" not in base_json:
            logger.warning(
                "No 'response' field in base JSON, returning fallback")
            return base_json

        response_data = base_json["response"]
        tasks = [
            self._enrich_locations(response_data),
            self._enrich_skills(response_data, alternative_skills)
        ]
        await asyncio.gather(*tasks)

        logger.info("Completed query analysis and enrichment")
        return base_json

    async def batch_analyze_queries(self, queries: List[str], alternative_skills: bool = False, max_concurrent: int = 5) -> List[Dict[str, Any]]:
        """
        For multiple queries, concurrency-limited with a semaphore.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _process(q: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.analyze_query(q, alternative_skills)

        tasks = [_process(q) for q in queries]
        return await asyncio.gather(*tasks)


###############################################################################
# DEMO
###############################################################################
if __name__ == "__main__":
    import time
    import datetime

    async def main():
        start_time = time.time()
        print(f"Starting analysis at: {datetime.datetime.now()}")

        hyde = HydeReasoning("azure-gpt-4.1-mini", "gemini")
        # test_query = "looking for AI researchers from OpenAI, Anthropic, or anyone who has worked at AI companies in the Bay Area"
        # test_query = "developers who have worked in ai in the last 2 years, and prior ml work in recommendation systems"
        test_query = "People Connected to Andreessen Horowitz, especially Indian"
        result = await hyde.analyze_query(test_query, alternative_skills=True)

        # Store result as JSON locally
        try:
            debug_file_path = os.path.join(
                'outputTest', f'hyde_result_{int(time.time())}.json')
            os.makedirs('outputTest', exist_ok=True)
            with open(debug_file_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Saved Hyde result to {debug_file_path}")
        except Exception as e:
            print(f"Error saving Hyde result: {str(e)}")

        end_time = time.time()
        print(f"Analysis completed at: {datetime.datetime.now()}")
        print(f"Total execution time: {end_time - start_time:.2f} seconds")

    asyncio.run(main())
