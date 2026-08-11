// Scene analysis: what a musical scene is looking for, using nothing but the
// search stream itself — no external database.
//
// Seed the scene with a few unambiguous marker words, find the pseudonyms that
// searched them, then look at everything else those people searched. Ranking
// by plain frequency would just return the global hits, so entries are ranked
// by lift: how much more common they are inside the scene than outside it.
//
// This is behavioural recommendation in miniature, and it works because
// pseudonyms are stable across time.
package main

import (
	"regexp"
	"sort"
	"strings"
)

type sceneEntry struct {
	Item       string  `json:"item"`
	SceneUsers int     `json:"scene_users"`
	AllUsers   int     `json:"all_users"`
	Lift       float64 `json:"lift"`
	// Average number of distinct queries per person carrying this word. Around
	// one means people asked for a record. Several means they are working
	// through a catalogue, which says more about the downloader than about the
	// scene.
	Depth float64 `json:"depth"`
}

// A word carried by this many distinct queries per person is a catalogue
// crawl, not a preference.
const catalogueCrawlDepth = 3.0

type sceneReport struct {
	Seed        string       `json:"seed"`
	SceneUsers  int          `json:"scene_users"`
	AllUsers    int          `json:"all_users"`
	Words       []sceneEntry `json:"words"`
	Queries     []sceneEntry `json:"queries"`
	Distinctive []sceneEntry `json:"distinctive_queries"`
}

// Queries this short or this generic carry no information about a scene.
func isUninformative(query string) bool {
	words := strings.Fields(query)
	return len(words) < 2
}

func buildSceneReport(records []queryRecord, seed *regexp.Regexp, topCount int) sceneReport {
	queriesByUser := map[string]map[string]bool{}
	usersByQuery := map[string]map[string]bool{}
	sceneUsers := map[string]bool{}

	for _, record := range records {
		if record.User == "" {
			continue
		}
		query := strings.Join(strings.Fields(strings.ToLower(record.Query)), " ")
		if query == "" {
			continue
		}
		if queriesByUser[record.User] == nil {
			queriesByUser[record.User] = map[string]bool{}
		}
		queriesByUser[record.User][query] = true

		if usersByQuery[query] == nil {
			usersByQuery[query] = map[string]bool{}
		}
		usersByQuery[query][record.User] = true

		if seed.MatchString(query) {
			sceneUsers[record.User] = true
		}
	}

	report := sceneReport{
		Seed:       seed.String(),
		SceneUsers: len(sceneUsers),
		AllUsers:   len(queriesByUser),
	}
	if report.SceneUsers == 0 || report.AllUsers == 0 {
		return report
	}

	sceneQueryCounts := map[string]int{}
	sceneWordCounts := map[string]int{}
	otherWordCounts := map[string]int{}
	sceneWordQueries := map[string]int{}

	for user, queries := range queriesByUser {
		inScene := sceneUsers[user]
		// Per user, per word: counted once no matter how many of their queries
		// carry it, so one person cannot manufacture a trend.
		queriesPerWord := map[string]int{}
		for query := range queries {
			if inScene {
				sceneQueryCounts[query]++
			}
			seen := map[string]bool{}
			for _, word := range wordPattern.FindAllString(query, -1) {
				if len([]rune(word)) > 3 && !seen[word] {
					seen[word] = true
					queriesPerWord[word]++
				}
			}
		}
		for word, queryCount := range queriesPerWord {
			if inScene {
				sceneWordCounts[word]++
				sceneWordQueries[word] += queryCount
			} else {
				otherWordCounts[word]++
			}
		}
	}

	sceneSize := float64(report.SceneUsers)
	outsideSize := float64(report.AllUsers - report.SceneUsers)
	if outsideSize < 1 {
		outsideSize = 1
	}

	// Words survive spelling and formatting differences between people looking
	// for the same thing, so they identify a scene far more reliably than whole
	// query strings do.
	var words []sceneEntry
	for word, count := range sceneWordCounts {
		if count < 5 {
			continue
		}
		// Smoothed: a word nobody outside the scene happened to type would
		// otherwise divide by zero and top the chart on five observations.
		outside := (float64(otherWordCounts[word]) + 1) / (outsideSize + 1)
		lift := (float64(count) / sceneSize) / outside
		depth := float64(sceneWordQueries[word]) / float64(count)

		// A catalogue crawl says what someone is downloading wholesale, not
		// what the scene likes. Discount it rather than hide it.
		if depth >= catalogueCrawlDepth {
			lift /= depth
		}
		words = append(words, sceneEntry{
			Item: word, SceneUsers: count, Lift: lift, Depth: depth,
		})
	}
	sortScene(words)
	report.Words = trimScene(words, topCount)

	// What the scene actually searches, by headcount: these are the records
	// people are hunting right now.
	var queries []sceneEntry
	var distinctive []sceneEntry
	for query, count := range sceneQueryCounts {
		if count < 2 || isUninformative(query) {
			continue
		}
		total := len(usersByQuery[query])
		lift := (float64(count) / sceneSize) / (float64(total) / float64(report.AllUsers))
		entry := sceneEntry{Item: query, SceneUsers: count, AllUsers: total, Lift: lift}
		queries = append(queries, entry)
		if count >= 3 {
			distinctive = append(distinctive, entry)
		}
	}

	sort.Slice(queries, func(first, second int) bool {
		if queries[first].SceneUsers != queries[second].SceneUsers {
			return queries[first].SceneUsers > queries[second].SceneUsers
		}
		return queries[first].Lift > queries[second].Lift
	})
	report.Queries = trimScene(queries, topCount)

	sortScene(distinctive)
	report.Distinctive = trimScene(distinctive, topCount)
	return report
}

func sortScene(entries []sceneEntry) {
	sort.Slice(entries, func(first, second int) bool {
		if entries[first].Lift != entries[second].Lift {
			return entries[first].Lift > entries[second].Lift
		}
		if entries[first].SceneUsers != entries[second].SceneUsers {
			return entries[first].SceneUsers > entries[second].SceneUsers
		}
		return entries[first].Item < entries[second].Item
	})
}

func trimScene(entries []sceneEntry, limit int) []sceneEntry {
	if limit > 0 && len(entries) > limit {
		return entries[:limit]
	}
	return entries
}
