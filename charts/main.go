// soulseek-charts builds demand charts from the archive written by the
// collector. It only reads: it never touches the network and never modifies
// the archive.
package main

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const archiveEnvironmentVariable = "SOULSEEK_ARCHIVE"

type queryRecord struct {
	Time  string `json:"time"`
	Query string `json:"query"`
	User  string `json:"user,omitempty"`
}

// Words that say nothing about what is being looked for.
var stopWords = map[string]bool{}

var stopWordList = strings.Fields(`
	the and you for with from your all out not was are her his one two who why
	how can get got she him our but has had were this that what when will just
	like have them there their then than into only over very very more much
	les des que der die das und ich una del las los por con
`)

// Asked-for encodings and media, counted separately from content words.
var formatWords = map[string]bool{}

var formatWordList = strings.Fields(`
	flac mp3 wav aiff aac ogg m4a alac ape dsd vinyl rip web 320 256 192 128
	24bit 16bit lossless
`)

var wordPattern = regexp.MustCompile(`[\p{L}\p{N}'\-]+`)

func init() {
	for _, word := range stopWordList {
		stopWords[word] = true
	}
	for _, word := range formatWordList {
		formatWords[word] = true
	}
}

type counter map[string]int

type entry struct {
	Item  string `json:"item"`
	Count int    `json:"count"`
}

// Ties are broken alphabetically so repeated runs give identical output.
func (counts counter) top(limit int) []entry {
	entries := make([]entry, 0, len(counts))
	for item, count := range counts {
		entries = append(entries, entry{item, count})
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

// A query ranked by how many different people looked for it. Demand is people,
// not keystrokes: one person working through a discography counts once per
// query, not forty times.
type demandEntry struct {
	Item     string `json:"item"`
	Users    int    `json:"users"`
	Searches int    `json:"searches"`
}

type report struct {
	Match       string        `json:"match,omitempty"`
	Scanned     int           `json:"scanned"`
	Total       int           `json:"total"`
	Unique      int           `json:"unique"`
	Searchers   int           `json:"searchers"`
	WithoutUser int           `json:"records_without_user"`
	First       string        `json:"first"`
	Last        string        `json:"last"`
	Demand      []demandEntry `json:"demand"`
	Searches    []entry       `json:"repeated_searches"`
	Words       []entry       `json:"words"`
	Phrases     []entry       `json:"phrases"`
	Formats     []entry       `json:"formats"`
	Genres      *genreReport  `json:"genres,omitempty"`
	PerSecond   float64       `json:"per_second"`
}

func main() {
	archiveDirectory := flag.String("data", "", "archive directory (defaults to $"+archiveEnvironmentVariable+", then ./data/raw)")
	topCount := flag.Int("top", 10, "how many entries per chart")
	since := flag.Duration("since", 0, "only consider records newer than this, e.g. 24h")
	section := flag.String("section", "all", "all, demand, genres, artists, searches, words, phrases or formats")
	asJSON := flag.Bool("json", false, "emit JSON instead of text")
	match := flag.String("match", "", "only consider queries matching this regular expression, case-insensitive")
	cachePath := flag.String("cache", "", "soulseek-resolve cache for genre charts (defaults next to the archive)")
	scene := flag.String("scene", "", "marker words for a scene: report what the people searching them also search")
	flag.Parse()

	var sceneSeed *regexp.Regexp
	if *scene != "" {
		compiled, err := regexp.Compile(`(?i)\b(` + *scene + `)\b`)
		if err != nil {
			fmt.Fprintf(os.Stderr, "bad -scene expression: %v\n", err)
			os.Exit(1)
		}
		sceneSeed = compiled
	}

	var filter *regexp.Regexp
	if *match != "" {
		compiled, err := regexp.Compile("(?i)" + *match)
		if err != nil {
			fmt.Fprintf(os.Stderr, "bad -match expression: %v\n", err)
			os.Exit(1)
		}
		filter = compiled
	}

	directory, err := resolveArchiveDirectory(*archiveDirectory)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	records, err := readArchive(directory, *since)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read archive: %v\n", err)
		os.Exit(1)
	}

	// The scene report needs everyone's searches, including people outside the
	// filter, so it runs before any filtering.
	if sceneSeed != nil {
		printScene(buildSceneReport(records, sceneSeed, *topCount))
		return
	}

	scanned := len(records)
	if filter != nil {
		kept := records[:0]
		for _, record := range records {
			if filter.MatchString(record.Query) {
				kept = append(kept, record)
			}
		}
		records = kept
	}

	if len(records) == 0 {
		fmt.Fprintln(os.Stderr, "nothing matched for the requested window")
		os.Exit(1)
	}

	result := buildReport(records, *topCount)
	result.Scanned = scanned
	result.Match = *match

	if *cachePath == "" {
		*cachePath = strings.TrimSuffix(strings.TrimSuffix(directory, "/"), "/raw") + "/musicbrainz.db"
	}
	if identifications, err := loadIdentifications(*cachePath); err == nil && len(identifications) > 0 {
		genres := buildGenreReport(records, identifications, *topCount)
		result.Genres = &genres
	}

	if *asJSON {
		encoder := json.NewEncoder(os.Stdout)
		encoder.SetIndent("", "  ")
		encoder.Encode(result)
		return
	}
	printReport(result, *section, directory)
}

func resolveArchiveDirectory(flagValue string) (string, error) {
	candidates := []string{flagValue, os.Getenv(archiveEnvironmentVariable), "data/raw"}
	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		information, err := os.Stat(candidate)
		if err == nil && information.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("no archive directory found\n"+
		"pass -data /path/to/collector/data/raw, or set %s", archiveEnvironmentVariable)
}

func readArchive(directory string, since time.Duration) ([]queryRecord, error) {
	names, err := os.ReadDir(directory)
	if err != nil {
		return nil, err
	}
	sort.Slice(names, func(first, second int) bool {
		return names[first].Name() < names[second].Name()
	})

	var cutoff time.Time
	if since > 0 {
		cutoff = time.Now().Add(-since)
	}

	var records []queryRecord
	for _, name := range names {
		if name.IsDir() {
			continue
		}
		path := filepath.Join(directory, name.Name())
		fileRecords, err := readArchiveFile(path, cutoff)
		if err != nil {
			fmt.Fprintf(os.Stderr, "skipping %s: %v\n", name.Name(), err)
			continue
		}
		records = append(records, fileRecords...)
	}
	return records, nil
}

func readArchiveFile(path string, cutoff time.Time) ([]queryRecord, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var source io.Reader = file
	if strings.HasSuffix(path, ".gz") {
		decompressor, err := gzip.NewReader(file)
		if err != nil {
			return nil, err
		}
		defer decompressor.Close()
		source = decompressor
	}

	var records []queryRecord
	scanner := bufio.NewScanner(source)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var record queryRecord
		if err := json.Unmarshal(line, &record); err != nil {
			continue
		}
		if !cutoff.IsZero() {
			observed, err := time.Parse(time.RFC3339, record.Time)
			if err != nil || observed.Before(cutoff) {
				continue
			}
		}
		records = append(records, record)
	}
	return records, scanner.Err()
}

func buildReport(records []queryRecord, topCount int) report {
	normalized := counter{}
	words := counter{}
	phrases := counter{}
	formats := counter{}
	unique := map[string]bool{}
	searchersByQuery := map[string]map[string]bool{}
	allSearchers := map[string]bool{}
	withoutUser := 0

	for _, record := range records {
		key := strings.Join(strings.Fields(strings.ToLower(record.Query)), " ")
		if key != "" {
			normalized[key]++
			if record.User == "" {
				withoutUser++
			} else {
				allSearchers[record.User] = true
				if searchersByQuery[key] == nil {
					searchersByQuery[key] = map[string]bool{}
				}
				searchersByQuery[key][record.User] = true
			}
		}
		unique[key] = true

		var contentWords []string
		for _, word := range wordPattern.FindAllString(strings.ToLower(record.Query), -1) {
			switch {
			case formatWords[word]:
				formats[word]++
			case len([]rune(word)) > 2 && !stopWords[word] && !isAllDigits(word):
				words[word]++
				contentWords = append(contentWords, word)
			}
		}
		for index := 0; index+1 < len(contentWords); index++ {
			phrases[contentWords[index]+" "+contentWords[index+1]]++
		}
	}

	repeated := counter{}
	for query, count := range normalized {
		if count > 1 {
			repeated[query] = count
		}
	}

	demand := make([]demandEntry, 0, len(searchersByQuery))
	for query, searchers := range searchersByQuery {
		if len(searchers) < 2 {
			continue
		}
		demand = append(demand, demandEntry{query, len(searchers), normalized[query]})
	}
	sort.Slice(demand, func(first, second int) bool {
		if demand[first].Users != demand[second].Users {
			return demand[first].Users > demand[second].Users
		}
		if demand[first].Searches != demand[second].Searches {
			return demand[first].Searches > demand[second].Searches
		}
		return demand[first].Item < demand[second].Item
	})
	if topCount > 0 && len(demand) > topCount {
		demand = demand[:topCount]
	}

	result := report{
		Total:       len(records),
		Unique:      len(unique),
		Searchers:   len(allSearchers),
		WithoutUser: withoutUser,
		First:       records[0].Time,
		Last:        records[len(records)-1].Time,
		Demand:      demand,
		Searches:    repeated.top(topCount),
		Words:       words.top(topCount),
		Phrases:     phrases.top(topCount),
		Formats:     formats.top(topCount),
	}

	firstSeen, firstError := time.Parse(time.RFC3339, result.First)
	lastSeen, lastError := time.Parse(time.RFC3339, result.Last)
	if firstError == nil && lastError == nil {
		if span := lastSeen.Sub(firstSeen).Seconds(); span > 0 {
			result.PerSecond = float64(result.Total) / span
		}
	}
	return result
}

func isAllDigits(word string) bool {
	for _, character := range word {
		if character < '0' || character > '9' {
			return false
		}
	}
	return true
}

func printScene(result sceneReport) {
	fmt.Printf("scene seed: %s\n", result.Seed)
	fmt.Printf("searchers: %d of %d touched this scene (%.1f%%)\n",
		result.SceneUsers, result.AllUsers,
		100*float64(result.SceneUsers)/float64(max(result.AllUsers, 1)))
	if result.SceneUsers == 0 {
		fmt.Println("\nnobody in this window searched those markers")
		return
	}

	fmt.Printf("\n=== names and words that mark this scene ===\n")
	fmt.Printf("    (depth = distinct queries per person; high means someone is\n")
	fmt.Printf("     working through a catalogue rather than picking records)\n\n")
	for position, item := range result.Words {
		note := ""
		if item.Depth >= 3 {
			note = "  catalogue crawl"
		}
		fmt.Printf("  %2d. x%-6.0f %3d people  depth %.1f  %s%s\n",
			position+1, item.Lift, item.SceneUsers, item.Depth, item.Item, note)
	}

	fmt.Printf("\n=== what these people are hunting ===\n")
	for position, item := range result.Queries {
		fmt.Printf("  %2d. %3d of %3d searchers  %s\n",
			position+1, item.SceneUsers, item.AllUsers, item.Item)
	}

	fmt.Printf("\n=== searched here far more than elsewhere ===\n")
	for position, item := range result.Distinctive {
		fmt.Printf("  %2d. x%-5.0f %3d of %3d searchers  %s\n",
			position+1, item.Lift, item.SceneUsers, item.AllUsers, item.Item)
	}
}

func printReport(result report, section, directory string) {
	fmt.Printf("archive: %s\n", directory)
	if result.Match != "" {
		fmt.Printf("filter:  /%s/ matched %d of %d scanned (%.2f%%)\n",
			result.Match, result.Total, result.Scanned,
			100*float64(result.Total)/float64(result.Scanned))
	}
	fmt.Printf("queries: %d, unique %d (%.1f%%), searchers %d\n",
		result.Total, result.Unique,
		100*float64(result.Unique)/float64(result.Total), result.Searchers)
	if result.WithoutUser > 0 {
		fmt.Printf("note:    %d records predate pseudonyms and carry no searcher\n",
			result.WithoutUser)
	}
	fmt.Printf("window:  %s .. %s", result.First, result.Last)
	if result.PerSecond > 0 {
		fmt.Printf("  (%.1f per second across the window)", result.PerSecond)
	}
	fmt.Println()

	show := func(name, title string, entries []entry) {
		if section != "all" && section != name {
			return
		}
		fmt.Printf("\n=== %s ===\n", title)
		if len(entries) == 0 {
			fmt.Println("  (nothing yet)")
			return
		}
		width := len(fmt.Sprint(entries[0].Count))
		for position, item := range entries {
			fmt.Printf("  %2d. %*d  %s\n", position+1, width, item.Count, item.Item)
		}
	}

	if section == "all" || section == "demand" {
		fmt.Printf("\n=== wanted by most people ===\n")
		if len(result.Demand) == 0 {
			fmt.Println("  (nothing searched by two different people yet)")
		} else {
			for position, item := range result.Demand {
				fmt.Printf("  %2d. %3d people, %4d searches  %s\n",
					position+1, item.Users, item.Searches, item.Item)
			}
		}
	}

	if result.Genres != nil && (section == "all" || section == "genres" || section == "artists") {
		fmt.Printf("\nidentified %d of %d queries via MusicBrainz (%.1f%%)\n",
			result.Genres.ResolvedCount, result.Genres.ConsideredKeys,
			100*result.Genres.ResolvedShare)
		if section != "artists" {
			show("genres", "genres by people", result.Genres.Genres)
		}
		if section != "genres" {
			show("artists", "artists by people", result.Genres.Artists)
		}
	}

	show("searches", "repeated searches", result.Searches)
	show("words", "words", result.Words)
	show("phrases", "phrases", result.Phrases)
	show("formats", "formats asked for", result.Formats)
}
