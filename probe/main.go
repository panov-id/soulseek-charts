// Step 0 of the Soulseek node idea: measure how many search queries a plain
// child node in the distributed network actually sees.
//
// No sharing, no downloading, no index. Log in, ask the server for possible
// parents, attach to one, count incoming DistribSearch messages.
//
// The username carried by every search request is deliberately read and
// discarded: the interesting signal is demand, not who wanted what.
package main

import (
	"bufio"
	"bytes"
	"crypto/md5"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	serverAddress = "server.slsknet.org:2242"

	// Version reported at login. Overridable to test whether the server gates
	// distributed network participation on a known client version.
	defaultMajorVersion = 200
	defaultMinorVersion = 1

	listeningPort        = 2234
	maximumMessageLength = 4 * 1024 * 1024

	serverCodeLogin           = 1
	serverCodeSetWaitPort         = 2
	serverCodeWatchUser           = 5
	serverCodeSetStatus           = 28
	serverCodePing                = 32
	serverCodeSharedFoldersFiles  = 35
	serverCodeCheckPrivileges     = 92

	userStatusOnline = 2
	serverCodeHaveNoParent    = 71
	serverCodeEmbeddedMessage = 93
	serverCodeAcceptChildren  = 100
	serverCodePossibleParents = 102
	serverCodeBranchLevel     = 126
	serverCodeBranchRoot      = 127

	initCodePeerInit = 1

	distributedCodeSearch      = 3
	distributedCodeBranchLevel = 4
	distributedCodeBranchRoot  = 5
)

var verboseLogging bool

// A real node has exactly one distributed parent. We race several candidates
// and keep the first ones that actually send us a search; the rest are
// dropped, otherwise every query would be counted once per connection.
//
// Keeping more than one parent is only useful for the coverage experiment:
// comparing the streams of two parents tells us whether a search reaches
// every node in the network or only part of it.
var acceptedParentCount atomic.Int32
var maximumParents int32 = 1

func debugLog(format string, arguments ...any) {
	if verboseLogging {
		fmt.Printf("[debug] "+format+"\n", arguments...)
	}
}

type messageBuilder struct{ buffer bytes.Buffer }

func (builder *messageBuilder) writeUint32(value uint32) {
	var encoded [4]byte
	binary.LittleEndian.PutUint32(encoded[:], value)
	builder.buffer.Write(encoded[:])
}

func (builder *messageBuilder) writeBool(value bool) {
	if value {
		builder.buffer.WriteByte(1)
		return
	}
	builder.buffer.WriteByte(0)
}

func (builder *messageBuilder) writeString(value string) {
	builder.writeUint32(uint32(len(value)))
	builder.buffer.WriteString(value)
}

// Server frame: uint32 length | uint32 code | contents
func buildServerMessage(code uint32, contents []byte) []byte {
	var frame messageBuilder
	frame.writeUint32(uint32(4 + len(contents)))
	frame.writeUint32(code)
	frame.buffer.Write(contents)
	return frame.buffer.Bytes()
}

// Initialisation and distributed frame: uint32 length | uint8 code | contents
func buildSmallCodeMessage(code uint8, contents []byte) []byte {
	var frame messageBuilder
	frame.writeUint32(uint32(1 + len(contents)))
	frame.buffer.WriteByte(code)
	frame.buffer.Write(contents)
	return frame.buffer.Bytes()
}

type messageReader struct {
	data   []byte
	offset int
}

func (reader *messageReader) readUint32() (uint32, error) {
	if reader.offset+4 > len(reader.data) {
		return 0, errors.New("truncated uint32")
	}
	value := binary.LittleEndian.Uint32(reader.data[reader.offset : reader.offset+4])
	reader.offset += 4
	return value, nil
}

func (reader *messageReader) readBool() (bool, error) {
	if reader.offset+1 > len(reader.data) {
		return false, errors.New("truncated bool")
	}
	value := reader.data[reader.offset]
	reader.offset++
	return value != 0, nil
}

func (reader *messageReader) readString() (string, error) {
	length, err := reader.readUint32()
	if err != nil {
		return "", err
	}
	if reader.offset+int(length) > len(reader.data) {
		return "", errors.New("truncated string")
	}
	value := string(reader.data[reader.offset : reader.offset+int(length)])
	reader.offset += int(length)
	return value, nil
}

func readFrame(reader *bufio.Reader) ([]byte, error) {
	var lengthBytes [4]byte
	if _, err := io.ReadFull(reader, lengthBytes[:]); err != nil {
		return nil, err
	}
	length := binary.LittleEndian.Uint32(lengthBytes[:])
	if length == 0 || length > maximumMessageLength {
		return nil, fmt.Errorf("implausible frame length %d", length)
	}
	payload := make([]byte, length)
	if _, err := io.ReadFull(reader, payload); err != nil {
		return nil, err
	}
	return payload, nil
}

// One line of the output file. There is no field for the searching user, on
// purpose. "Parent" is the peer that relayed the query to us — needed to
// compare coverage between parents, not to identify anyone.
type queryRecord struct {
	Time   string `json:"time"`
	Query  string `json:"query"`
	Parent string `json:"parent"`
	Level  uint32 `json:"level"`
}

type searchStatistics struct {
	mutex        sync.Mutex
	startedAt    time.Time
	totalQueries int
	wordCounts   map[string]int
	recentSample []string
	outputWriter *bufio.Writer
}

func newSearchStatistics(outputWriter *bufio.Writer) *searchStatistics {
	return &searchStatistics{
		startedAt:    time.Now(),
		wordCounts:   map[string]int{},
		outputWriter: outputWriter,
	}
}

// The username that arrives with every DistribSearch is deliberately not
// passed in here: we keep the demand, not the person behind it.
func (statistics *searchStatistics) recordQuery(query, parent string, branchLevel uint32) {
	statistics.mutex.Lock()
	defer statistics.mutex.Unlock()

	statistics.totalQueries++
	for _, word := range strings.Fields(strings.ToLower(query)) {
		if len(word) > 2 {
			statistics.wordCounts[word]++
		}
	}
	statistics.recentSample = append(statistics.recentSample, query)
	if len(statistics.recentSample) > 20 {
		statistics.recentSample = statistics.recentSample[1:]
	}

	if statistics.outputWriter == nil {
		return
	}
	line, err := json.Marshal(queryRecord{
		Time:   time.Now().UTC().Format(time.RFC3339),
		Query:  query,
		Parent: parent,
		Level:  branchLevel,
	})
	if err != nil {
		return
	}
	statistics.outputWriter.Write(line)
	statistics.outputWriter.WriteByte('\n')
}

func (statistics *searchStatistics) report() {
	statistics.mutex.Lock()
	defer statistics.mutex.Unlock()

	if statistics.outputWriter != nil {
		statistics.outputWriter.Flush()
	}

	elapsed := time.Since(statistics.startedAt).Seconds()
	fmt.Printf("\n=== %.0fs elapsed | %d queries | %.1f per second ===\n",
		elapsed, statistics.totalQueries, float64(statistics.totalQueries)/elapsed)

	type wordCount struct {
		word  string
		count int
	}
	counts := make([]wordCount, 0, len(statistics.wordCounts))
	for word, count := range statistics.wordCounts {
		counts = append(counts, wordCount{word, count})
	}
	sort.Slice(counts, func(first, second int) bool {
		return counts[first].count > counts[second].count
	})

	fmt.Print("top words:")
	for index := 0; index < len(counts) && index < 15; index++ {
		fmt.Printf(" %s(%d)", counts[index].word, counts[index].count)
	}
	fmt.Println()

	for _, query := range statistics.recentSample {
		fmt.Printf("  > %s\n", query)
	}
}

func login(connection net.Conn, username, password string, majorVersion, minorVersion uint32) error {
	digest := md5.Sum([]byte(username + password))

	var contents messageBuilder
	contents.writeString(username)
	contents.writeString(password)
	contents.writeUint32(majorVersion)
	contents.writeString(hex.EncodeToString(digest[:]))
	contents.writeUint32(minorVersion)

	_, err := connection.Write(buildServerMessage(serverCodeLogin, contents.buffer.Bytes()))
	return err
}

func sendServerBool(connection net.Conn, code uint32, value bool) error {
	var contents messageBuilder
	contents.writeBool(value)
	_, err := connection.Write(buildServerMessage(code, contents.buffer.Bytes()))
	return err
}

func sendServerUint32(connection net.Conn, code uint32, value uint32) error {
	var contents messageBuilder
	contents.writeUint32(value)
	_, err := connection.Write(buildServerMessage(code, contents.buffer.Bytes()))
	return err
}

func sendServerString(connection net.Conn, code uint32, value string) error {
	var contents messageBuilder
	contents.writeString(value)
	_, err := connection.Write(buildServerMessage(code, contents.buffer.Bytes()))
	return err
}

func sendEmptyServerMessage(connection net.Conn, code uint32) error {
	_, err := connection.Write(buildServerMessage(code, nil))
	return err
}

// The server expects a ping at least once in a while to keep the session alive.
func keepConnectionAlive(connection net.Conn) {
	for range time.Tick(60 * time.Second) {
		if err := sendEmptyServerMessage(connection, serverCodePing); err != nil {
			return
		}
		debugLog("ping sent")
	}
}

// Server code 35: number of shared folders and files. We share nothing during
// the measurement, but the server expects to hear about it.
func sendSharedFoldersFiles(connection net.Conn, folders, files uint32) error {
	var contents messageBuilder
	contents.writeUint32(folders)
	contents.writeUint32(files)
	_, err := connection.Write(buildServerMessage(serverCodeSharedFoldersFiles, contents.buffer.Bytes()))
	return err
}

type parentCandidate struct {
	username string
	address  string
}

func connectToParent(candidate parentCandidate, ownUsername string,
	statistics *searchStatistics, firstSearch chan<- string) {

	connection, err := net.DialTimeout("tcp", candidate.address, 5*time.Second)
	if err != nil {
		debugLog("dial %s (%s) failed: %v", candidate.username, candidate.address, err)
		return
	}
	defer connection.Close()
	debugLog("connected to %s (%s)", candidate.username, candidate.address)

	var contents messageBuilder
	contents.writeString(ownUsername)
	contents.writeString("D")
	contents.writeUint32(0)
	if _, err := connection.Write(buildSmallCodeMessage(initCodePeerInit, contents.buffer.Bytes())); err != nil {
		return
	}

	reader := bufio.NewReader(connection)
	branchLevel := uint32(0)
	branchRoot := ""
	announced := false

	for {
		connection.SetReadDeadline(time.Now().Add(120 * time.Second))
		payload, err := readFrame(reader)
		if err != nil {
			debugLog("read from %s ended: %v", candidate.username, err)
			return
		}

		code := payload[0]
		body := messageReader{data: payload[1:]}
		debugLog("distributed code %d from %s (%d bytes)", code, candidate.username, len(payload))

		switch code {
		case distributedCodeBranchLevel:
			branchLevel, _ = body.readUint32()

		case distributedCodeBranchRoot:
			branchRoot, _ = body.readString()

		case distributedCodeSearch:
			body.readUint32() // identifier, always 49
			body.readString() // username of the searcher, read and dropped
			body.readUint32() // token
			query, err := body.readString()
			if err != nil {
				continue
			}

			if !announced {
				if acceptedParentCount.Add(1) > maximumParents {
					acceptedParentCount.Add(-1)
					debugLog("dropping %s: parent slots are full", candidate.username)
					return
				}
				announced = true
				fmt.Printf("parent %s accepted us, branch level %d, root %q\n",
					candidate.username, branchLevel, branchRoot)
				select {
				case firstSearch <- branchRoot:
				default:
				}
			}

			statistics.recordQuery(query, candidate.username, branchLevel)
		}
	}
}

func main() {
	duration := flag.Duration("duration", 5*time.Minute, "how long to measure")
	outputPath := flag.String("output", "/data/searches.jsonl", "where to append captured queries")
	verbose := flag.Bool("verbose", false, "log every protocol message received")
	majorVersion := flag.Uint("major", defaultMajorVersion, "client major version reported at login")
	minorVersion := flag.Uint("minor", defaultMinorVersion, "client minor version reported at login")
	parents := flag.Int("parents", 1, "how many distributed parents to keep at once")
	flag.Parse()
	maximumParents = int32(*parents)
	verboseLogging = *verbose

	username := os.Getenv("SOULSEEK_USERNAME")
	password := os.Getenv("SOULSEEK_PASSWORD")
	if username == "" || password == "" {
		fmt.Fprintln(os.Stderr, "set SOULSEEK_USERNAME and SOULSEEK_PASSWORD")
		os.Exit(1)
	}

	connection, err := net.DialTimeout("tcp", serverAddress, 10*time.Second)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot reach server: %v\n", err)
		os.Exit(1)
	}
	defer connection.Close()

	debugLog("logging in as version %d.%d", *majorVersion, *minorVersion)
	if err := login(connection, username, password, uint32(*majorVersion), uint32(*minorVersion)); err != nil {
		fmt.Fprintf(os.Stderr, "login failed: %v\n", err)
		os.Exit(1)
	}

	outputFile, err := os.OpenFile(*outputPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		fmt.Fprintf(os.Stderr, "cannot open output file %s: %v\n", *outputPath, err)
		os.Exit(1)
	}
	defer outputFile.Close()
	outputWriter := bufio.NewWriter(outputFile)
	defer outputWriter.Flush()

	statistics := newSearchStatistics(outputWriter)
	firstSearch := make(chan string, 1)
	reader := bufio.NewReader(connection)
	deadline := time.Now().Add(*duration)

	go func() {
		for range time.Tick(10 * time.Second) {
			statistics.report()
		}
	}()

	// Once a parent has adopted us, tell the server where we sit in the tree.
	go func() {
		branchRoot := <-firstSearch
		sendServerBool(connection, serverCodeHaveNoParent, false)
		sendServerUint32(connection, serverCodeBranchLevel, 1)
		sendServerString(connection, serverCodeBranchRoot, branchRoot)
	}()

	for time.Now().Before(deadline) {
		connection.SetReadDeadline(deadline)
		payload, err := readFrame(reader)
		if err != nil {
			break
		}

		body := messageReader{data: payload}
		code, err := body.readUint32()
		if err != nil {
			continue
		}

		switch code {
		case serverCodeLogin:
			success, _ := body.readBool()
			if !success {
				reason, _ := body.readString()
				fmt.Fprintf(os.Stderr, "login rejected: %s\n", reason)
				os.Exit(1)
			}
			greeting, _ := body.readString()
			fmt.Printf("logged in. server says: %s\n", greeting)

			// The full post-login sequence a real client performs. Announcing
			// our status is what was missing: without it the server never
			// starts offering distributed parents.
			sendEmptyServerMessage(connection, serverCodeCheckPrivileges)
			sendServerUint32(connection, serverCodeSetWaitPort, listeningPort)
			sendServerUint32(connection, serverCodeSetStatus, userStatusOnline)
			sendSharedFoldersFiles(connection, 0, 0)
			sendServerString(connection, serverCodeWatchUser, username)

			// No parent yet: branch level 0 with ourselves as the branch root.
			// AcceptChildren is true because the distributed network is
			// reciprocal — a node that refuses to relay is a bad citizen.
			sendServerBool(connection, serverCodeHaveNoParent, true)
			sendServerString(connection, serverCodeBranchRoot, username)
			sendServerUint32(connection, serverCodeBranchLevel, 0)
			sendServerBool(connection, serverCodeAcceptChildren, true)

			go keepConnectionAlive(connection)

		case serverCodePossibleParents:
			count, _ := body.readUint32()
			debugLog("PossibleParents: %d candidates", count)
			for index := uint32(0); index < count; index++ {
				candidateUsername, _ := body.readString()
				address, _ := body.readUint32()
				port, err := body.readUint32()
				if err != nil {
					break
				}
				// The uint32 is decoded little-endian, which puts the first
				// octet of the address in the high byte.
				candidate := parentCandidate{
					username: candidateUsername,
					address: fmt.Sprintf("%d.%d.%d.%d:%d",
						address>>24&0xff, address>>16&0xff,
						address>>8&0xff, address&0xff, port),
				}
				debugLog("candidate %s at %s", candidateUsername, candidate.address)
				go connectToParent(candidate, username, statistics, firstSearch)
			}

		case serverCodeEmbeddedMessage:
			// Only branch roots receive these. Unreachable in practice, but
			// worth noticing if it ever happens.
			fmt.Println("received an embedded distributed message from the server")

		default:
			debugLog("server code %d (%d bytes)", code, len(payload))
		}
	}

	fmt.Println("\n=== final ===")
	statistics.report()
}
