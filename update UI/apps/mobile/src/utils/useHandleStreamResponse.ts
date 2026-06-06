import React from 'react';

interface UseHandleStreamResponseProps {
	onChunk: (content: string) => void;
	onFinish: (content: string) => void;
}

export function useHandleStreamResponse({ onChunk, onFinish }: UseHandleStreamResponseProps) {
	const handleStreamResponse = React.useCallback(
		async (response: Response) => {
			if (response.body) {
				const reader = response.body.getReader();
				if (reader) {
					const decoder = new TextDecoder();
					let content = '';
					while (true) {
						const { done, value } = await reader.read();
						if (done) {
							onFinish(content);
							break;
						}
						const chunk = decoder.decode(value, { stream: true });
						content += chunk;
						onChunk(content);
					}
				}
			}
		},
		[onChunk, onFinish]
	);
	return handleStreamResponse;
}

export default useHandleStreamResponse;
