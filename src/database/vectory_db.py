import json

from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.vector_stores.types import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as LLMOpenAI
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.query_engine import ToolRetrieverRouterQueryEngine

from openai import OpenAI

from src.libs import SafeSemanticSplitter
from src.libs.const import OPENAI_API_KEY, DATABASE_URL
from src.libs.rag_prompts import EMAIL_SUGGESTION_PROMPT, EMAIL_SYSTEM_PROMPT

Settings.chunk_size = 8192

llm = LLMOpenAI(model="gpt-5-nano", api_key=OPENAI_API_KEY)

client = OpenAI(api_key=OPENAI_API_KEY)


class VectorDB:
    def __init__(
        self,
    ):
        self.database_url = DATABASE_URL
        self.vector_store = PGVectorStore.from_params(
            database=DATABASE_URL,
            table_name="email_vectors",
            embed_dim=1536,  # text-embedding-3-small dimension
        )
        self.transaction_store = PGVectorStore.from_params(
            database=DATABASE_URL,
            table_name="transaction_vectors",
            embed_dim=1536,
        )
        self.embed_model = OpenAIEmbedding(api_key=OPENAI_API_KEY, model="text-embedding-3-small")
        Settings.embed_model = self.embed_model

        self.pipeline = IngestionPipeline(
            transformations=[
                SafeSemanticSplitter(
                    buffer_size=1,
                    breakpoint_percentile_threshold=95,
                    embed_model=self.embed_model,
                ),
                self.embed_model,
            ],
            vector_store=self.vector_store,
        )
        self.transaction_pipeline = IngestionPipeline(
            transformations=[
                SafeSemanticSplitter(
                    buffer_size=1,
                    breakpoint_percentile_threshold=95,
                    embed_model=self.embed_model,
                ),
                self.embed_model,
            ],
            vector_store=self.transaction_store,
        )

    def create_dense_embedding(self, doc_text):
        """
        Generate dense vector embeddings using OpenAI.
        """
        embedding = (
            client.embeddings.create(input=doc_text, model="text-embedding-3-small")
            .data[0]
            .embedding
        )
        return embedding

    def _metadata_to_json(self, metadata: str):
        # Split the input string into lines
        lines = metadata.strip().split("\n")

        # Initialize an empty dictionary to hold the parsed data
        data = {}

        # Iterate over each line
        for line in lines:
            # Split each line by the first occurrence of ':'
            key, value = line.split(": ", 1)
            data[key] = value

        # Convert the dictionary to a JSON string
        return data

    def insert(self, documents: list[Document], user_id: str):
        # Add user_id to metadata for filtering
        for doc in documents:
            doc.metadata["user_id"] = str(user_id)

        self.pipeline.run(documents=documents)
        return True

    def insert_transactions(self, documents: list[Document], user_id: str):
        # Add user_id to metadata for filtering
        for doc in documents:
            doc.metadata["user_id"] = str(user_id)

        response = []
        nodes = self.transaction_pipeline.run(documents=documents)
        for node in nodes:
            try:
                metadata = self._metadata_to_json(node.get_metadata_str())
            except Exception as e:
                raise ValueError(e)
            vectors = node.get_embedding()
            response.append({"metadata": metadata, "vectors": vectors})

        return response

    def query(self, query: str, top_k: int, user_id: str):
        index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            embed_model=self.embed_model,
        )
        query_engine = index.as_query_engine(
            similarity_top_k=top_k, filters={"user_id": str(user_id)}
        )
        response = query_engine.query(query)
        return response

    def chat(self, query: str, top_k: int, user_id: str):
        index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            embed_model=self.embed_model,
        )
        query_engine = index.as_query_engine(
            llm=llm, streaming=True, similarity_top_k=top_k, filters={"user_id": str(user_id)}
        )
        formatted_query = EMAIL_SYSTEM_PROMPT + query
        response = query_engine.query(formatted_query)

        for text in response.response_gen:
            yield json.dumps({"data": text}) + "\n"

    async def suggest(
        self,
        query: str,
        user_id: str,
        name: str,
        filter: dict,
        top_k: int = 50,
        writing_style="",
    ):
        # Combine user_id filter with any additional filters
        combined_filter = {"user_id": str(user_id)}
        if filter:
            combined_filter.update(filter)

        index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            embed_model=self.embed_model,
        )
        query_engine = index.as_query_engine(
            llm=llm, streaming=True, similarity_top_k=top_k, filters=combined_filter
        )
        formatted_query = (
            EMAIL_SUGGESTION_PROMPT.format(user=name, writing_style=writing_style) + query
        )
        response = query_engine.query(formatted_query)
        for text in response.response_gen:
            yield json.dumps({"data": text}) + "\n"

    def list(self, user_id: str):
        # PGVector doesn't have a direct list equivalent
        # This would need to be implemented as a database query if needed
        raise NotImplementedError("List operation not implemented for PGVector")

    def get(self, ids, user_id: str):
        # PGVector doesn't have a direct get equivalent
        # This would need to be implemented as a database query if needed
        raise NotImplementedError("Get operation not implemented for PGVector")

    def update(self, id, user_id: str, update_metadata_dict: dict):
        # PGVector doesn't have a direct update equivalent
        # This would need to be implemented as a database query if needed
        raise NotImplementedError("Update operation not implemented for PGVector")
