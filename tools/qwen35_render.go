// Build from the separately pinned Ollama module checkout. This driver uses
// the maintained renderer directly; it implements no alternate chat template.
// Scope: one user text message, no tools/images/model-defined messages/system.
package main

import (
	"fmt"
	"io"
	"os"
	"unicode/utf8"

	"github.com/ollama/ollama/api"
	"github.com/ollama/ollama/model/renderers"
)

func main() {
	if len(os.Args) != 3 || (os.Args[2] != "false" && os.Args[2] != "true") {
		fmt.Fprintln(os.Stderr, "usage: qwen35-render PROMPT_UTF8 THINKING_true_or_false")
		os.Exit(2)
	}
	handle, err := os.Open(os.Args[1])
	if err != nil {
		panic(err)
	}
	defer handle.Close()
	raw, err := io.ReadAll(io.LimitReader(handle, 4*1024*1024+1))
	if err != nil || len(raw) > 4*1024*1024 || !utf8.Valid(raw) {
		fmt.Fprintln(os.Stderr, "Require bounded valid UTF-8 prompt")
		os.Exit(2)
	}
	rendered, err := renderers.RenderWithRenderer("qwen3.5", []api.Message{{Role: "user", Content: string(raw)}}, nil, &api.ThinkValue{Value: os.Args[2] == "true"})
	if err != nil {
		panic(err)
	}
	if _, err := os.Stdout.WriteString(rendered); err != nil {
		panic(err)
	}
}
