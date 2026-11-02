// Offline CPU vocabulary-only tokenization. No backend/context/inference API.
#include "llama.h"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include <cstring>

int main(int argc, char ** argv) {
    if (argc != 4 || (std::strcmp(argv[3], "0") && std::strcmp(argv[3], "1"))) {
        std::fprintf(stderr, "usage: gguf-tokenize ZERO_TENSOR_GGUF INPUT_UTF8 ADD_SPECIAL_0_OR_1\n");
        return 2;
    }
    std::ifstream meta(argv[1], std::ios::binary);
    unsigned char header[24] = {};
    if (!meta.read(reinterpret_cast<char *>(header), sizeof(header)) ||
        std::memcmp(header, "GGUF", 4) || header[4] != 3 || header[5] || header[6] || header[7]) {
        std::fprintf(stderr, "Require little-endian GGUF v3 metadata export\n"); return 2;
    }
    for (int i = 8; i < 16; ++i) {
        if (header[i]) { std::fprintf(stderr, "Refuse tensor-bearing container\n"); return 2; }
    }
    meta.close();
    std::ifstream input(argv[2], std::ios::binary | std::ios::ate);
    if (!input || input.tellg() < 0 || input.tellg() > 4 * 1024 * 1024) {
        std::fprintf(stderr, "Input missing or exceeds 4 MiB\n"); return 2;
    }
    input.seekg(0);
    std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    llama_model_params params = llama_model_default_params();
    ggml_backend_dev_t no_devices[] = {nullptr};
    params.devices = no_devices;
    params.n_gpu_layers = 0;
    params.vocab_only = true;
    params.check_tensors = false;
    params.load_mtp = false;
    llama_model * model = llama_model_load_from_file(argv[1], params);
    if (!model) { std::fprintf(stderr, "Vocabulary-only metadata parse failed\n"); return 2; }
    const llama_vocab * vocab = llama_model_get_vocab(model);
    const bool add_special = argv[3][0] == '1';
    int count = llama_tokenize(vocab, text.data(), static_cast<int>(text.size()), nullptr, 0, add_special, true);
    if (count > 0 || count < -8 * 1024 * 1024) { llama_model_free(model); return 2; }
    std::vector<llama_token> tokens(static_cast<size_t>(-count));
    count = llama_tokenize(vocab, text.data(), static_cast<int>(text.size()), tokens.data(), static_cast<int>(tokens.size()), add_special, true);
    if (count < 0) { llama_model_free(model); return 2; }
    std::printf("{\"vocabulary_tokens\":%d,\"add_special\":%s,\"parse_special\":true,\"input_utf8_bytes\":%zu,\"count\":%d,\"tokens\":[", llama_vocab_n_tokens(vocab), add_special ? "true" : "false", text.size(), count);
    for (int i = 0; i < count; ++i) std::printf("%s%d", i ? "," : "", tokens[i]);
    std::printf("]}\n");
    llama_model_free(model);
}
