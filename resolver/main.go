// soulseek-resolve turns raw search strings into identified releases using
// MusicBrainz, so charts can be grouped by artist and genre instead of by
// whatever words people happened to type.
//
// Everything resolved is cached locally. MusicBrainz allows roughly one
// request per second per IP address, so the cache is what makes this usable
// at all: a query is looked up once and reused forever after.
package main

import (
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

const (
	serviceRoot = "https://musicbrainz.org/ws/2"

	// MusicBrainz declines requests from an IP that averages more than one per
	// second. A little slack keeps us clearly inside the limit.
	requestInterval = 1100 * time.Millisecond

)

// Noise that hurts matching: format, quality and source markers people append
// to what they actually want.
var noisePattern = regexp.MustCompile(`(?i)\b(flac|mp3|wav|aiff|aac|ogg|m4a|alac|ape|dsd|lossless|vinyl|rip|web|cd|320|256|192|128|24 ?bit|16 ?bit|1080p|720p|2160p|4k|x264|x265|mkv|mp4)\b`)

var punctuationPattern = regexp.MustCompile(`[^\p{L}\p{N}\s]+`)

type archiveRecord struct {
	Query string `json:"query"`
	User  string `json:"user,omitempty"`
}

type demandRow struct {
	query    string
	users    int
	searches int
}

type match struct {
	Found        bool
	Kind         string // "artist" or "release"
	Score        int
	ReleaseTitle string
	ArtistName   string
	ArtistID     string
	Genres       string
}

// A short query is almost always someone looking for an artist, not for an
// album with that exact title. Searching releases first turns "radiohead" into
// a track called "Radiohead" by an unrelated act.
const shortQueryTokenCount = 3

// How much of the query the matched names must account for. Without this the
// top hit is accepted even when it shares a single common word.
const minimumTokenCoverage = 0.6

func main() {
	archiveDirectory := flag.String("data", os.Getenv("SOULSEEK_ARCHIVE"), "archive directory")
	cachePath := flag.String("cache", "", "SQLite cache path (defaults next to the archive)")
	since := flag.Duration("since", 24*time.Hour, "window to build demand from")
	topCount := flag.Int("top", 50, "how many demand entries to resolve")
	minimumUsers := flag.Int("min-users", 2, "ignore queries wanted by fewer people than this")
	callBudget := flag.Int("budget", 200, "maximum MusicBrainz requests for this run")
	refresh := flag.Bool("refresh", false, "re-resolve even when a cached answer exists")
	contact := flag.String("contact", os.Getenv("SOULSEEK_CONTACT"), "contact e-mail or URL for the User-Agent header")
	offline := flag.Bool("offline", false, "use only the cache, make no requests")
	flag.Parse()

	if *archiveDirectory == "" {
		fmt.Fprintln(os.Stderr, "set -data or SOULSEEK_ARCHIVE")
		os.Exit(1)
	}
	if *contact == "" && !*offline {
		fmt.Fprintln(os.Stderr,
			"MusicBrainz requires a contact in the User-Agent: pass -contact or set SOULSEEK_CONTACT")
		os.Exit(1)
	}

	if *cachePath == "" {
		*cachePath = strings.TrimSuffix(strings.TrimSuffix(*archiveDirectory, "/"), "/raw") + "/musicbrainz.db"
	}

	cache, err := openCache(*cachePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot open cache: %v\n", err)
		os.Exit(1)
	}
	defer cache.Close()

	demand, err := readDemand(*archiveDirectory, *since, *minimumUsers)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot read archive: %v\n", err)
		os.Exit(1)
	}
	if len(demand) == 0 {
		fmt.Fprintln(os.Stderr, "no queries met the -min-users threshold in this window")
		os.Exit(1)
	}
	if len(demand) > *topCount {
		demand = demand[:*topCount]
	}

	client := &musicBrainzClient{
		httpClient: &http.Client{Timeout: 30 * time.Second},
		userAgent:  fmt.Sprintf("soulseek-charts/0.1 ( %s )", *contact),
	}

	fmt.Printf("resolving %d queries, cache %s\n\n", len(demand), *cachePath)

	resolved := 0
	spent := 0
	for _, row := range demand {
		normalized := normalizeForSearch(row.query)
		if normalized == "" {
			continue
		}

		found, hit := cache.lookup(normalized)
		if *refresh {
			found = false
		}
		if !found {
			if *offline || spent >= *callBudget {
				printRow(row, match{}, "not cached")
				continue
			}
			result, err := client.resolve(normalized)
			spent++
			if err != nil {
				printRow(row, match{}, "error: "+err.Error())
				continue
			}
			if result.Found && result.ArtistID != "" && spent < *callBudget {
				genres, genresFromCache, err := cache.artistGenres(client, result.ArtistID)
				if !genresFromCache {
					spent++
				}
				if err == nil {
					result.Genres = genres
				}
			}
			cache.store(normalized, result)
			hit = result
		}

		if hit.Found {
			resolved++
		}
		printRow(row, hit, "")
	}

	fmt.Printf("\nresolved %d of %d, %d MusicBrainz requests spent\n",
		resolved, len(demand), spent)
}

func printRow(row demandRow, hit match, note string) {
	fmt.Printf("%3d people %5d searches  %s\n", row.users, row.searches, row.query)
	switch {
	case note != "":
		fmt.Printf("      -> %s\n", note)
	case !hit.Found:
		fmt.Printf("      -> no confident match\n")
	case hit.Kind == "artist":
		line := fmt.Sprintf("      -> artist: %s", hit.ArtistName)
		if hit.Genres != "" {
			line += "  [" + hit.Genres + "]"
		}
		fmt.Println(line)
	default:
		line := fmt.Sprintf("      -> %s — %s", hit.ArtistName, hit.ReleaseTitle)
		if hit.Genres != "" {
			line += "  [" + hit.Genres + "]"
		}
		fmt.Println(line)
	}
}

// Strips format and quality noise, punctuation and repeated spaces. What is
// left is much closer to "artist album" than the raw string.
func normalizeForSearch(query string) string {
	cleaned := noisePattern.ReplaceAllString(strings.ToLower(query), " ")
	cleaned = punctuationPattern.ReplaceAllString(cleaned, " ")
	return strings.Join(strings.Fields(cleaned), " ")
}

type musicBrainzClient struct {
	httpClient *http.Client
	userAgent  string
	lastCall   time.Time
}

// Every call goes through here so the one-request-per-second rule holds no
// matter which endpoint is being used.
func (client *musicBrainzClient) get(endpoint string, parameters url.Values) ([]byte, error) {
	if wait := requestInterval - time.Since(client.lastCall); wait > 0 {
		time.Sleep(wait)
	}

	parameters.Set("fmt", "json")
	address := fmt.Sprintf("%s/%s?%s", serviceRoot, endpoint, parameters.Encode())

	var lastError error
	for attempt := 0; attempt < 3; attempt++ {
		request, err := http.NewRequest(http.MethodGet, address, nil)
		if err != nil {
			return nil, err
		}
		request.Header.Set("User-Agent", client.userAgent)

		response, err := client.httpClient.Do(request)
		client.lastCall = time.Now()
		if err != nil {
			lastError = err
			time.Sleep(time.Duration(attempt+1) * 2 * time.Second)
			continue
		}

		body, readError := io.ReadAll(response.Body)
		response.Body.Close()

		if response.StatusCode == http.StatusServiceUnavailable {
			// Being throttled: back off and try again rather than give up.
			lastError = fmt.Errorf("rate limited")
			time.Sleep(time.Duration(attempt+1) * 3 * time.Second)
			continue
		}
		if response.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("status %d", response.StatusCode)
		}
		if readError != nil {
			return nil, readError
		}
		return body, nil
	}
	return nil, lastError
}

type releaseSearchResponse struct {
	Releases []struct {
		Score        int    `json:"score"`
		Title        string `json:"title"`
		ArtistCredit []struct {
			Name   string `json:"name"`
			Artist struct {
				ID   string `json:"id"`
				Name string `json:"name"`
			} `json:"artist"`
		} `json:"artist-credit"`
	} `json:"releases"`
}

func (client *musicBrainzClient) resolve(query string) (match, error) {
	if len(strings.Fields(query)) <= shortQueryTokenCount {
		result, err := client.resolveArtist(query)
		if err != nil {
			return match{}, err
		}
		if result.Found {
			return result, nil
		}
	}
	return client.resolveRelease(query)
}

type artistSearchResponse struct {
	Artists []struct {
		ID    string `json:"id"`
		Name  string `json:"name"`
		Score int    `json:"score"`
	} `json:"artists"`
}

// Accepted only on an exact name match: anything looser reintroduces the very
// mistakes this path exists to prevent.
func (client *musicBrainzClient) resolveArtist(query string) (match, error) {
	parameters := url.Values{}
	parameters.Set("query", query)
	parameters.Set("limit", "1")

	body, err := client.get("artist", parameters)
	if err != nil {
		return match{}, err
	}

	var response artistSearchResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return match{}, err
	}
	if len(response.Artists) == 0 {
		return match{}, nil
	}

	artist := response.Artists[0]
	if normalizeForSearch(artist.Name) != query {
		return match{}, nil
	}
	return match{
		Found:      true,
		Kind:       "artist",
		Score:      artist.Score,
		ArtistName: artist.Name,
		ArtistID:   artist.ID,
	}, nil
}

func (client *musicBrainzClient) resolveRelease(query string) (match, error) {
	parameters := url.Values{}
	parameters.Set("query", query)
	parameters.Set("limit", "1")

	body, err := client.get("release", parameters)
	if err != nil {
		return match{}, err
	}

	var response releaseSearchResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return match{}, err
	}
	if len(response.Releases) == 0 {
		return match{}, nil
	}

	release := response.Releases[0]
	result := match{
		Found:        true,
		Kind:         "release",
		Score:        release.Score,
		ReleaseTitle: release.Title,
	}
	if len(release.ArtistCredit) > 0 {
		result.ArtistName = release.ArtistCredit[0].Artist.Name
		result.ArtistID = release.ArtistCredit[0].Artist.ID
	}

	if tokenCoverage(query, result.ArtistName+" "+result.ReleaseTitle) < minimumTokenCoverage {
		return match{}, nil
	}
	return result, nil
}

// Share of the query's words that appear in the matched names.
func tokenCoverage(query, candidate string) float64 {
	queryTokens := strings.Fields(query)
	if len(queryTokens) == 0 {
		return 0
	}
	candidateTokens := map[string]bool{}
	for _, token := range strings.Fields(normalizeForSearch(candidate)) {
		candidateTokens[token] = true
	}
	present := 0
	for _, token := range queryTokens {
		if candidateTokens[token] {
			present++
		}
	}
	return float64(present) / float64(len(queryTokens))
}

type artistGenresResponse struct {
	Genres []struct {
		Name  string `json:"name"`
		Count int    `json:"count"`
	} `json:"genres"`
}

func (client *musicBrainzClient) genresForArtist(artistID string) (string, error) {
	parameters := url.Values{}
	parameters.Set("inc", "genres")

	body, err := client.get("artist/"+artistID, parameters)
	if err != nil {
		return "", err
	}

	var response artistGenresResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return "", err
	}
	sort.Slice(response.Genres, func(first, second int) bool {
		return response.Genres[first].Count > response.Genres[second].Count
	})

	names := make([]string, 0, 3)
	for index, genre := range response.Genres {
		if index == 3 {
			break
		}
		names = append(names, genre.Name)
	}
	return strings.Join(names, ", "), nil
}

type cacheStore struct {
	database *sql.DB
}

func openCache(path string) (*cacheStore, error) {
	database, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	statements := []string{
		`CREATE TABLE IF NOT EXISTS resolved_queries (
			query TEXT PRIMARY KEY,
			found INTEGER NOT NULL,
			kind TEXT NOT NULL DEFAULT '',
			score INTEGER NOT NULL,
			release_title TEXT NOT NULL,
			artist_name TEXT NOT NULL,
			artist_id TEXT NOT NULL,
			genres TEXT NOT NULL,
			resolved_at TEXT NOT NULL
		)`,
		`CREATE TABLE IF NOT EXISTS artist_genres (
			artist_id TEXT PRIMARY KEY,
			genres TEXT NOT NULL,
			resolved_at TEXT NOT NULL
		)`,
	}
	for _, statement := range statements {
		if _, err := database.Exec(statement); err != nil {
			return nil, err
		}
	}
	// Caches written before artist matching existed lack this column.
	database.Exec(`ALTER TABLE resolved_queries ADD COLUMN kind TEXT NOT NULL DEFAULT ''`)
	return &cacheStore{database: database}, nil
}

func (cache *cacheStore) Close() { cache.database.Close() }

func (cache *cacheStore) lookup(query string) (bool, match) {
	row := cache.database.QueryRow(
		`SELECT found, kind, score, release_title, artist_name, artist_id, genres
		 FROM resolved_queries WHERE query = ?`, query)

	var found int
	var result match
	if err := row.Scan(&found, &result.Kind, &result.Score, &result.ReleaseTitle,
		&result.ArtistName, &result.ArtistID, &result.Genres); err != nil {
		return false, match{}
	}
	result.Found = found == 1
	return true, result
}

func (cache *cacheStore) store(query string, result match) {
	found := 0
	if result.Found {
		found = 1
	}
	cache.database.Exec(
		`INSERT INTO resolved_queries
		     (query, found, kind, score, release_title, artist_name, artist_id, genres, resolved_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		 ON CONFLICT(query) DO UPDATE SET
		     found = excluded.found, kind = excluded.kind, score = excluded.score,
		     release_title = excluded.release_title, artist_name = excluded.artist_name,
		     artist_id = excluded.artist_id, genres = excluded.genres,
		     resolved_at = excluded.resolved_at`,
		query, found, result.Kind, result.Score, result.ReleaseTitle,
		result.ArtistName, result.ArtistID, result.Genres,
		time.Now().UTC().Format(time.RFC3339))
}

// Genres are cached per artist, not per query: one artist covers many queries,
// which is where most of the request budget is saved.
func (cache *cacheStore) artistGenres(client *musicBrainzClient, artistID string) (string, bool, error) {
	var genres string
	err := cache.database.QueryRow(
		`SELECT genres FROM artist_genres WHERE artist_id = ?`, artistID).Scan(&genres)
	if err == nil {
		return genres, true, nil
	}

	genres, err = client.genresForArtist(artistID)
	if err != nil {
		return "", false, err
	}
	cache.database.Exec(
		`INSERT INTO artist_genres (artist_id, genres, resolved_at) VALUES (?, ?, ?)
		 ON CONFLICT(artist_id) DO UPDATE SET genres = excluded.genres, resolved_at = excluded.resolved_at`,
		artistID, genres, time.Now().UTC().Format(time.RFC3339))
	return genres, false, nil
}
