// Grouping demand by genre and artist, using the identifications that
// soulseek-resolve has already cached. Nothing here talks to MusicBrainz: if a
// query was never resolved, it simply does not appear in these charts.
package main

import (
	"database/sql"
	"regexp"
	"sort"
	"strings"

	_ "modernc.org/sqlite"
)

// Must match the normalisation soulseek-resolve applies before caching, or
// nothing will ever be found in the cache.
var resolverNoisePattern = regexp.MustCompile(`(?i)\b(flac|mp3|wav|aiff|aac|ogg|m4a|alac|ape|dsd|lossless|vinyl|rip|web|cd|320|256|192|128|24 ?bit|16 ?bit|1080p|720p|2160p|4k|x264|x265|mkv|mp4)\b`)

var resolverPunctuationPattern = regexp.MustCompile(`[^\p{L}\p{N}\s]+`)

func normalizeForResolver(query string) string {
	cleaned := resolverNoisePattern.ReplaceAllString(strings.ToLower(query), " ")
	cleaned = resolverPunctuationPattern.ReplaceAllString(cleaned, " ")
	return strings.Join(strings.Fields(cleaned), " ")
}

type identification struct {
	artist string
	genres []string
}

func loadIdentifications(cachePath string) (map[string]identification, error) {
	database, err := sql.Open("sqlite", cachePath)
	if err != nil {
		return nil, err
	}
	defer database.Close()

	rows, err := database.Query(
		`SELECT query, artist_name, genres FROM resolved_queries WHERE found = 1`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	identifications := map[string]identification{}
	for rows.Next() {
		var query, artist, genres string
		if err := rows.Scan(&query, &artist, &genres); err != nil {
			continue
		}
		entry := identification{artist: artist}
		for _, genre := range strings.Split(genres, ",") {
			genre = strings.TrimSpace(genre)
			if genre != "" {
				entry.genres = append(entry.genres, genre)
			}
		}
		identifications[query] = entry
	}
	return identifications, rows.Err()
}

type genreReport struct {
	Genres         []entry `json:"genres"`
	Artists        []entry `json:"artists"`
	ResolvedShare  float64 `json:"resolved_share"`
	ResolvedCount  int     `json:"resolved_queries"`
	ConsideredKeys int     `json:"considered_queries"`
}

// Demand is counted in people: every distinct searcher of a query is credited
// once to each genre of the matched artist. Counting searches instead would
// let one persistent person define an entire genre's popularity.
func buildGenreReport(records []queryRecord, identifications map[string]identification,
	topCount int) genreReport {

	searchersByQuery := map[string]map[string]bool{}
	for _, record := range records {
		if record.User == "" {
			continue
		}
		key := strings.Join(strings.Fields(strings.ToLower(record.Query)), " ")
		if key == "" {
			continue
		}
		if searchersByQuery[key] == nil {
			searchersByQuery[key] = map[string]bool{}
		}
		searchersByQuery[key][record.User] = true
	}

	genreSearchers := map[string]map[string]bool{}
	artistSearchers := map[string]map[string]bool{}
	resolved := 0

	for query, searchers := range searchersByQuery {
		entry, known := identifications[normalizeForResolver(query)]
		if !known {
			continue
		}
		resolved++

		if entry.artist != "" {
			if artistSearchers[entry.artist] == nil {
				artistSearchers[entry.artist] = map[string]bool{}
			}
			for searcher := range searchers {
				artistSearchers[entry.artist][searcher] = true
			}
		}
		for _, genre := range entry.genres {
			if genreSearchers[genre] == nil {
				genreSearchers[genre] = map[string]bool{}
			}
			for searcher := range searchers {
				genreSearchers[genre][searcher] = true
			}
		}
	}

	report := genreReport{
		ResolvedCount:  resolved,
		ConsideredKeys: len(searchersByQuery),
	}
	if len(searchersByQuery) > 0 {
		report.ResolvedShare = float64(resolved) / float64(len(searchersByQuery))
	}
	report.Genres = topOfSets(genreSearchers, topCount)
	report.Artists = topOfSets(artistSearchers, topCount)
	return report
}

func topOfSets(sets map[string]map[string]bool, limit int) []entry {
	entries := make([]entry, 0, len(sets))
	for name, members := range sets {
		entries = append(entries, entry{Item: name, Count: len(members)})
	}
	sort.Slice(entries, func(first, second int) bool {
		if entries[first].Count != entries[second].Count {
			return entries[first].Count > entries[second].Count
		}
		return entries[first].Item < entries[second].Item
	})
	if limit > 0 && len(entries) > limit {
		entries = entries[:limit]
	}
	return entries
}
