import { neon, NeonQueryFunction } from '@neondatabase/serverless';

type SqlQueryFunction = NeonQueryFunction<false, false> & {
  query: NeonQueryFunction<false, false>;
};

const NullishQueryFunction = (() => {
  throw new Error(
    'No database connection string was provided to `neon()`. Perhaps process.env.DATABASE_URL has not been set'
  );
}) as any as SqlQueryFunction;

NullishQueryFunction.transaction = (() => {
  throw new Error(
    'No database connection string was provided to `neon()`. Perhaps process.env.DATABASE_URL has not been set'
  );
}) as any as NeonQueryFunction<false, false>['transaction'];
NullishQueryFunction.query = NullishQueryFunction;

const sql = (
  process.env.DATABASE_URL ? neon(process.env.DATABASE_URL) : NullishQueryFunction
) as SqlQueryFunction;
sql.query = sql;

export default sql;
