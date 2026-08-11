// Reading the collector's archive and turning it into a demand list: queries
// ranked by how many different people looked for them.
package main

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

func readDemand(directory string, since time.Duration, minimumUsers int) ([]demandRow, error) {
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, err
	}
	sort.Slice(entries, func(first, second int) bool {
		return entries[first].Name() < entries[second].Name()
	})

	var cutoff time.Time
	if since > 0 {
		cutoff = time.Now().Add(-since)
	}

	searches := map[string]int{}
	searchers := map[string]map[string]bool{}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		if err := scanArchiveFile(path, cutoff, searches, searchers); err != nil {
			continue
		}
	}

	rows := make([]demandRow, 0, len(searchers))
	for query, people := range searchers {
		if len(people) < minimumUsers {
			continue
		}
		rows = append(rows, demandRow{query: query, users: len(people), searches: searches[query]})
	}
	sort.Slice(rows, func(first, second int) bool {
		if rows[first].users != rows[second].users {
			return rows[first].users > rows[second].users
		}
		if rows[first].searches != rows[second].searches {
			return rows[first].searches > rows[second].searches
		}
		return rows[first].query < rows[second].query
	})
	return rows, nil
}

func scanArchiveFile(path string, cutoff time.Time,
	searches map[string]int, searchers map[string]map[string]bool) error {

	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()

	var source io.Reader = file
	if strings.HasSuffix(path, ".gz") {
		decompressor, err := gzip.NewReader(file)
		if err != nil {
			return err
		}
		defer decompressor.Close()
		source = decompressor
	}

	scanner := bufio.NewScanner(source)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var record struct {
			Time  string `json:"time"`
			Query string `json:"query"`
			User  string `json:"user"`
		}
		if err := json.Unmarshal(line, &record); err != nil {
			continue
		}
		if !cutoff.IsZero() {
			observed, err := time.Parse(time.RFC3339, record.Time)
			if err != nil || observed.Before(cutoff) {
				continue
			}
		}

		key := strings.Join(strings.Fields(strings.ToLower(record.Query)), " ")
		if key == "" {
			continue
		}
		searches[key]++
		if record.User == "" {
			continue
		}
		if searchers[key] == nil {
			searchers[key] = map[string]bool{}
		}
		searchers[key][record.User] = true
	}
	return scanner.Err()
}
