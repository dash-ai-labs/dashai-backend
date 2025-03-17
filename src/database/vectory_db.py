import json

from llama_index.core import Document, ServiceContext, Settings, VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as LLMOpenAI
from llama_index.vector_stores.pinecone import PineconeVectorStore
from openai import OpenAI
from pinecone import Pinecone
from pinecone.grpc import PineconeGRPC

from src.libs import SafeSemanticSplitter
from src.libs.const import OPENAI_API_KEY, PINECONE_API_KEY
from src.libs.rag_prompts import EMAIL_SUGGESTION_PROMPT, EMAIL_SYSTEM_PROMPT

Settings.chunk_size = 8192

llm = LLMOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)

client = OpenAI(api_key=OPENAI_API_KEY)

pic = Pinecone(api_key=PINECONE_API_KEY)


class VectorDB:
    def __init__(
        self,
    ):
        self.api_key = PINECONE_API_KEY
        self.pc = PineconeGRPC(api_key=self.api_key)
        self.index = self.pc.Index("email-index")
        self.transaction_index = self.pc.Index("transaction-vectors")
        self.vector_store = PineconeVectorStore(pinecone_index=self.index, add_sparse_vector=True)
        self.transaction_store = PineconeVectorStore(pinecone_index=self.transaction_index)
        self.embed_model = OpenAIEmbedding(api_key=OPENAI_API_KEY, model="text-embedding-3-small")
        self.service_context = ServiceContext.from_defaults(embed_model=self.embed_model)

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

    def create_sparse_vector_embedding(self, doc_text):
        """
        Generate sparse vectors for a given document using LlamaIndex.
        """
        sparse_embedding = pic.inference.embed(
            model="pinecone-sparse-english-v0",
            inputs=[doc_text],
            parameters={"input_type": "passage", "return_tokens": True},
        )
        return sparse_embedding

    def create_sparse_vector_query(self, doc_text):

        sparse_embedding = pic.inference.embed(
            model="pinecone-sparse-english-v0",
            inputs=[doc_text],
            parameters={"input_type": "query", "return_tokens": True},
        )
        return sparse_embedding

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
        self.pipeline.vector_store = PineconeVectorStore(
            pinecone_index=self.index, namespace=str(user_id), batch_size=1
        )
        self.pipeline.run(documents=documents, namespace=str(user_id))

        return True

    def insert_transactions(self, documents: list[Document], user_id: str):
        self.transaction_pipeline.vector_store = PineconeVectorStore(
            pinecone_index=self.transaction_index, namespace=str(user_id)
        )
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

    def hybrid_score_norm(self, dense, sparse, alpha: float):
        """Hybrid score using a convex combination

        alpha * dense + (1 - alpha) * sparse

        Args:
            dense: Array of floats representing
            sparse: a dict of `indices` and `values`
            alpha: scale between 0 and 1
        """
        if alpha < 0 or alpha > 1:
            raise ValueError("Alpha must be between 0 and 1")
        hs = {"indices": sparse["indices"], "values": [v * (1 - alpha) for v in sparse["values"]]}
        return [v * alpha for v in dense], hs

    def query(self, query: str, top_k: int, user_id: str):
        xq = client.embeddings.create(input=query, model="text-embedding-3-small").data[0].embedding
        sparse_vector = self.create_sparse_vector_query(query)
        sparse_vec = {
            "indices": sparse_vector.data[0].sparse_indices,
            "values": sparse_vector.data[0].sparse_values,
        }
        hdense, hsparse = self.hybrid_score_norm(xq, sparse_vec, alpha=0.75)

        res = self.index.query(
            vector=hdense,
            top_k=top_k,
            namespace=user_id,
            include_metadata=True,
            sparse_vector=hsparse,
        )
        return res

    def chat(self, query: str, top_k: int, user_id: str):
        index = VectorStoreIndex.from_vector_store(
            vector_store=PineconeVectorStore(pinecone_index=self.index, namespace=str(user_id)),
            embed_model=self.embed_model,
        )
        query_engine = index.as_query_engine(llm=llm, streaming=True, similarity_top_k=top_k)
        formatted_query = EMAIL_SYSTEM_PROMPT + query
        response = query_engine.query(formatted_query)
        for text in response.response_gen:
            yield json.dumps({"data": text}) + "\n"

    def suggest(
        self,
        query: str,
        user_id: str,
        filter: dict,
        top_k: int = 50,
    ):
        index = VectorStoreIndex.from_vector_store(
            vector_store=PineconeVectorStore(pinecone_index=self.index, namespace=str(user_id)),
            embed_model=self.embed_model,
        )
        query_engine = index.as_query_engine(
            llm=llm, streaming=True, similarity_top_k=top_k, filter=filter
        )
        formatted_query = EMAIL_SUGGESTION_PROMPT + query
        response = query_engine.query(formatted_query)
        for text in response.response_gen:
            yield text

    def list(self, namespace: str):
        return self.index.list(namespace=str(namespace))

    def get(self, ids, namespace: str):
        return self.index.fetch(ids=ids, namespace=str(namespace))

    def update(self, id, namespace: str, update_metadata_dict: dict):
        return self.index.update(id=id, namespace=str(namespace), set_metadata=update_metadata_dict)
